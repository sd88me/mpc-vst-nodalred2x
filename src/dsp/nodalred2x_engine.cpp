/* NodalRed2x for MPC: gearmulator's Clavia Nord Lead 2x emulation (n2xLib: the 68331 firmware plus two DSP56362) as an mpc-vst-plugins
 * engine (wrapper/engine.h). GPL-3.0.
 *
 * One emulator thread per instance runs n2x::Device through synthLib::Plugin, fills a ring of int16 stereo, and render() only drains it.
 * Single mode, part A on MIDI channel 1. The instrument holds no sounds of its own (its patch memory is flash the emulator never has), so
 * a sound is 66 parameter bytes this engine keeps: edits go to the firmware as MIDI controllers (most) or a whole single dump (the morph
 * amounts), a sound is loaded as a single dump. Sounds come from a small built-in STARTERS bank and from <data_dir>/banks/ (.syx / .mid
 * files of Nord Lead 2 / 2x single dumps, 99 to a bank). The parameter table is generated (tools/gen_params.py -> nodalred2x_params.h).
 *
 * ROM: <data_dir>/roms/*.bin (512 kB Nord Lead 2x flash dump). None ships. Favourites: <data_dir>/favourites.dat. */
#include "fast_cores.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <strings.h>
#include <exception>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <sched.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <thread>
#include <unistd.h>
#include <unordered_map>
#include <vector>

extern "C" {
#include "engine.h"
}

#include "synthLib/deviceTypes.h"
#include "synthLib/midiTypes.h"
#include "synthLib/midiToSysex.h"
#include "synthLib/plugin.h"
#include "n2xLib/n2xdevice.h"
#include "n2xLib/n2xstate.h"
#include "n2xLib/n2xmiditypes.h"
#include "n2xLib/n2xtypes.h"

#include "nodalred2x_params.h"

namespace {

constexpr int kRate = 44100, kBlock = 128;
constexpr int kRingFrames = 16384;               // power of two
constexpr int kTargetFill = 1024;                // frames the emulator thread keeps queued (~23 ms)
constexpr int kBoostFill = 2688;                 // ~60 ms, for 400 ms after a sound load (EMULATOR_PORTS.md section 3)
constexpr int kNumBytes = 66;                    // parameter bytes of a single
constexpr int kFavSlots = 64;
constexpr int kMaxBanks = 64;
constexpr size_t kRomSize = 524288;

using Patch = std::array<uint8_t, kNumBytes>;

FILE *g_log = nullptr;
void xlog(const char *fmt, ...) {
    if (!g_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

long long mono_ms() { return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

/* CPU ticks of this process's emulator threads (ours "NRemu", gearmulator's "DSP ..." and the 68331's), for the STATS readout */
long emu_thread_ticks(pid_t host_tid) {
    long total = 0;
    DIR *d = opendir("/proc/self/task");
    if (!d) return 0;
    while (struct dirent *e = readdir(d)) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char path[64], line[512];
        snprintf(path, sizeof path, "/proc/self/task/%s/comm", e->d_name);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        const bool ours = fgets(line, sizeof line, f) && (!strncmp(line, "NRemu", 5) || !strncmp(line, "DSP", 3) || !strncmp(line, "MC68", 4));
        fclose(f);
        if (!ours || atoi(e->d_name) == host_tid) continue;
        snprintf(path, sizeof path, "/proc/self/task/%s/stat", e->d_name);
        f = fopen(path, "r");
        if (!f) continue;
        if (fgets(line, sizeof line, f)) {
            const char *q = strrchr(line, ')');
            unsigned long ut = 0, st = 0;
            if (q && sscanf(q + 2, "%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu", &ut, &st) == 2) total += (long)(ut + st);
        }
        fclose(f);
    }
    closedir(d);
    return total;
}

/* single parameter -> MIDI controller (n2xmiditypes.h), -1: none (a single dump carries it) */
const int8_t *cc_table() {
    static int8_t t[kNumBytes];
    static bool init = false;
    if (!init) {
        memset(t, -1, sizeof t);
        const struct { int p, cc; } m[] = {
            {n2x::Gain, 7}, {n2x::OctaveShift, 17}, {n2x::ModWheelDest, 18}, {n2x::Unison, 16}, {n2x::VoiceMode, 15}, {n2x::Auto, 65}, {n2x::Portamento, 5},
            {n2x::Lfo1Rate, 19}, {n2x::Lfo1Waveform, 20}, {n2x::Lfo1Dest, 21}, {n2x::Lfo1Level, 22}, {n2x::Lfo2Rate, 23}, {n2x::Lfo2Dest, 24},
            {n2x::ArpRange, 25}, {n2x::ModEnvA, 26}, {n2x::ModEnvD, 27}, {n2x::ModEnvDest, 28}, {n2x::ModEnvLevel, 29}, {n2x::O1Waveform, 30},
            {n2x::O2Waveform, 31}, {n2x::O2Pitch, 78}, {n2x::O2PitchFine, 33}, {n2x::FmDepth, 70}, {n2x::O2Keytrack, 34}, {n2x::PW, 79}, {n2x::Sync, 35},
            {n2x::Mix, 8}, {n2x::AmpEnvA, 73}, {n2x::AmpEnvD, 36}, {n2x::AmpEnvS, 37}, {n2x::AmpEnvR, 72}, {n2x::FilterEnvA, 38}, {n2x::FilterEnvD, 39},
            {n2x::FilterEnvS, 40}, {n2x::FilterEnvR, 41}, {n2x::FilterType, 44}, {n2x::Cutoff, 74}, {n2x::Resonance, 42}, {n2x::FilterEnvAmount, 43},
            {n2x::FilterVelocity, 45}, {n2x::FilterKeytrack, 46}};
        for (auto &e : m) t[e.p] = (int8_t)e.cc;
        init = true;
    }
    return t;
}

enum CmdType : uint8_t { C_MIDI, C_PARAM, C_LOAD, C_PANIC, C_MULTI };
struct Cmd {
    CmdType type = C_MIDI;
    uint8_t m[3] = {0, 0, 0};
    int a = 0, b = 0;
    Patch patch{};
};

struct Sound { std::string name; Patch p; };
struct Bank { std::string name; std::vector<Sound> sounds; };

struct Inst {
    std::string dir;
    std::thread th;
    std::atomic<bool> stop{false}, ready{false}, failed{false};

    std::vector<int16_t> ring = std::vector<int16_t>(kRingFrames * 2);
    std::atomic<uint32_t> wr{0}, rd{0};
    std::atomic<uint32_t> underruns{0};
    std::atomic<uint32_t> ring_min{0xffffffffu}, burst_max{0};
    std::atomic<int> emu_cpu{0};

    std::mutex qm;
    std::vector<Cmd> q;

    std::atomic<uint8_t> raw[kNumBytes];                      // the current sound's parameter bytes, what the UI reads and writes
    std::atomic<int> multi[4];                                // lfo1_sync, lfo2_sync, bend_range, unison_detune
    std::atomic<int> bank{0}, preset{0}, page{0}, gain{70}, bank_page{0};
    std::atomic<uint32_t> load_gen{0}, rev{1};
    std::mutex sm;
    char status[96] = "Starting...";
    char rom_name[96] = "";
    std::vector<Bank> banks;                                  // 0 = STARTERS, then one per 99 sounds of each file in banks/
    std::atomic<double> host_bpm{0.0}, host_ppq{-1.0};
    std::atomic<bool> host_playing{false};

    std::mutex fm;
    int fav_count = 0, fav_current = -1;
    uint32_t fav_stamp = 0;
    char fav_name[kFavSlots][24] = {};
    Patch fav_patch[kFavSlots];
    std::atomic<long long> fav_list_ms{-100000};
    std::mutex stm;
    char stats_cache[96] = "";
    int stats_cpu = -1;

    void bump() { rev.fetch_add(1, std::memory_order_relaxed); }
    void set_status(const char *s) {
        { std::lock_guard<std::mutex> l(sm); snprintf(status, sizeof status, "%s", s); }
        bump();
    }
    void push(Cmd &&c) { std::lock_guard<std::mutex> l(qm); if (q.size() < 4096) q.push_back(std::move(c)); }
};

int bank_count(Inst *in) { return (int)in->banks.size(); }
int bank_size(Inst *in, int b) { return b >= 0 && b < bank_count(in) ? (int)in->banks[b].sounds.size() : 0; }

/* ---- parameter conversion */
std::unordered_map<std::string, int> &np_index() {
    static std::unordered_map<std::string, int> m = [] {
        std::unordered_map<std::string, int> r;
        for (int i = 0; i < NR_NUM_PARAMS; i++) r[g_nr_params[i].key] = i;
        return r;
    }();
    return m;
}
int value_to_raw(const nr_param_t &p, int v) {
    switch (p.kind) {
    case 1: return clampi(v, 0, p.hi);
    case 5: return v & 0xff;
    default: return clampi(v + p.off, p.lo, p.hi);
    }
}
int raw_to_value(const nr_param_t &p, int raw) {
    switch (p.kind) {
    case 1: return clampi(raw, 0, p.hi);
    case 5: return (int)(int8_t)raw;
    default: return clampi(raw - p.off, p.lo - p.off, p.hi - p.off);
    }
}
int field_get(const nr_param_t &p, uint8_t byte) { return p.mask ? (byte >> p.shift) & p.mask : byte; }
uint8_t field_set(const nr_param_t &p, uint8_t byte, int raw) {
    if (!p.mask) return (uint8_t)raw;
    return (uint8_t)((byte & ~(p.mask << p.shift)) | ((raw & p.mask) << p.shift));
}

Patch default_patch() {
    n2x::State::SingleDump sd;
    n2x::State::createDefaultSingle(sd, 0, n2x::SingleDumpBankEditBuffer);
    Patch p;
    for (int i = 0; i < kNumBytes; i++) p[i] = (uint8_t)(sd[6 + 2 * i] | (sd[7 + 2 * i] << 4));
    return p;
}
void set_v(Patch &p, const char *key, int v) {      // by VST value
    auto it = np_index().find(key);
    if (it == np_index().end()) return;
    const nr_param_t &q = g_nr_params[it->second];
    p[q.idx] = field_set(q, p[q.idx], value_to_raw(q, v));
}

/* the built-in STARTERS bank: sounds made for this plugin from the parameters, so there is something to play before sound sets are added */
std::vector<Sound> starters() {
    struct S { const char *name; std::vector<std::pair<const char *, int>> v; };
    const std::vector<S> list = {
        {"INIT", {}},
        {"SAW LEAD", {{"O1Waveform", 1}, {"O2Waveform", 1}, {"O2PitchFine", 6}, {"Mix", 0}, {"Cutoff", 85}, {"Resonance", 30}, {"FilterEnvAmount", 40}, {"FilterEnvD", 60},
                      {"FilterEnvS", 60}, {"AmpEnvR", 40}, {"FilterType", 1}, {"VoiceMode", 1}, {"Portamento", 15}}},
        {"PULSE BASS", {{"O1Waveform", 0}, {"O2Waveform", 0}, {"PW", 40}, {"O2Pitch", -12}, {"Cutoff", 40}, {"Resonance", 50}, {"FilterEnvAmount", 80},
                        {"FilterEnvD", 40}, {"FilterEnvS", 0}, {"AmpEnvD", 60}, {"AmpEnvS", 100}, {"VoiceMode", 0}, {"FilterType", 1}}},
        {"SOFT PAD", {{"O1Waveform", 1}, {"O2Waveform", 1}, {"O2PitchFine", 4}, {"AmpEnvA", 70}, {"AmpEnvR", 80}, {"FilterEnvA", 60}, {"FilterEnvS", 80},
                      {"Cutoff", 70}, {"FilterType", 0}, {"Lfo1Rate", 30}, {"Lfo1Dest", 1}, {"Lfo1Level", 20}}},
        {"PLUCK", {{"O1Waveform", 2}, {"O2Waveform", 1}, {"O2Pitch", 12}, {"AmpEnvD", 45}, {"AmpEnvS", 0}, {"FilterEnvD", 35}, {"FilterEnvS", 0}, {"Cutoff", 50},
                   {"FilterEnvAmount", 70}, {"Resonance", 20}}},
        {"SYNC SWEEP", {{"Sync", 1}, {"O1Waveform", 1}, {"O2Waveform", 1}, {"O2Pitch", 7}, {"ModEnvDest", 0}, {"ModEnvLevel", 40}, {"ModEnvD", 70}, {"Cutoff", 100}}},
        {"RING BELL", {{"RingMod", 1}, {"O1Waveform", 3}, {"O2Waveform", 2}, {"O2Pitch", 19}, {"AmpEnvD", 90}, {"AmpEnvS", 0}, {"AmpEnvR", 60}, {"Cutoff", 127}}},
        {"ACID", {{"O1Waveform", 1}, {"FilterType", 1}, {"Cutoff", 30}, {"Resonance", 100}, {"FilterEnvAmount", 90}, {"FilterEnvD", 30}, {"FilterEnvS", 0},
                  {"VoiceMode", 0}, {"Portamento", 20}, {"Distortion", 1}, {"Auto", 1}}},
    };
    std::vector<Sound> out;
    for (const auto &s : list) {
        Sound so;
        so.name = s.name;
        so.p = default_patch();
        for (const auto &kv : s.v) set_v(so.p, kv.first, kv.second);
        out.push_back(so);
    }
    return out;
}

/* ---- sound-set files: Nord Lead 2 / 2x single dumps, F0 33 <dev> 04 <bank> <prog> + 66 parameters as nibble pairs [+ 10 name bytes] F7 */
bool parse_single(const std::vector<uint8_t> &m, Patch &p, std::string &name) {
    if ((m.size() != n2x::g_singleDumpSize && m.size() != n2x::g_singleDumpWithNameSize) || m[0] != 0xf0 || m[1] != 0x33 || m[3] != 0x04 || m.back() != 0xf7) return false;
    if (m[4] == 0 && m[5] > 3) return false;
    if (m[4] > 10 || (m[4] >= 5 && m[4] < 10)) { /* only single banks: edit buffer (0), banks 1-4 (A-D) and the later singles (up to 10) */ }
    for (int i = 0; i < kNumBytes; i++) p[i] = (uint8_t)((m[6 + 2 * i] & 0xf) | ((m[7 + 2 * i] & 0xf) << 4));
    name.clear();
    if (m.size() == n2x::g_singleDumpWithNameSize) {
        for (int i = 0; i < 10; i++) { const uint8_t c = m[6 + 2 * kNumBytes + i]; name += (char)(c >= 32 && c < 127 ? c : ' '); }
        while (!name.empty() && name.back() == ' ') name.pop_back();
    }
    return true;
}

void scan_banks(Inst *in) {
    const std::string dir = in->dir + "/banks";
    DIR *d = opendir(dir.c_str());
    if (!d) return;
    std::vector<std::string> files;
    while (struct dirent *e = readdir(d)) {
        const std::string n = e->d_name;
        if (n.size() > 4 && (!strcasecmp(n.c_str() + n.size() - 4, ".mid") || !strcasecmp(n.c_str() + n.size() - 4, ".syx"))) files.push_back(n);
    }
    closedir(d);
    std::sort(files.begin(), files.end());
    for (const auto &n : files) {
        synthLib::SysexBufferList msgs;
        if (!synthLib::MidiToSysex::extractSysexFromFile(msgs, dir + "/" + n)) { xlog("[banks] %s: no sysex", n.c_str()); continue; }
        std::vector<Sound> singles;
        for (auto &m : msgs) {
            Sound s;
            std::string nm;
            if (parse_single(std::vector<uint8_t>(m.begin(), m.end()), s.p, nm)) { s.name = nm; singles.push_back(s); }
        }
        xlog("[banks] %s: %zu messages, %zu singles", n.c_str(), msgs.size(), singles.size());
        if (singles.empty()) continue;
        std::string stem = n.substr(0, n.size() - 4);
        for (auto &c : stem) c = (char)toupper((unsigned char)(c == '_' ? ' ' : c));
        if (stem.size() > 15) stem.resize(15);
        const int nb = (int)(singles.size() + NR_PER_BANK - 1) / NR_PER_BANK;
        for (int k = 0; k < nb && (int)in->banks.size() < kMaxBanks; k++) {
            Bank b;
            b.name = nb > 1 ? stem + " " + (char)('A' + k) : stem;
            b.sounds.assign(singles.begin() + k * NR_PER_BANK, singles.begin() + std::min<size_t>(singles.size(), (size_t)(k + 1) * NR_PER_BANK));
            in->banks.push_back(std::move(b));
        }
    }
    xlog("[banks] %zu banks", in->banks.size());
}

/* ---- MIDI building */
synthLib::SMidiEvent cc_event(int cc, int v) { return synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0xb0, (uint8_t)cc, (uint8_t)(v & 0x7f)); }

synthLib::SMidiEvent single_dump_event(const Patch &p) {
    n2x::State::SingleDump sd;
    n2x::State::createDefaultSingle(sd, 0, n2x::SingleDumpBankEditBuffer);          // header for part A, edit buffer
    for (int i = 0; i < kNumBytes; i++) { sd[6 + 2 * i] = p[i] & 0xf; sd[7 + 2 * i] = p[i] >> 4; }
    synthLib::SMidiEvent e(synthLib::MidiEventSource::Host);
    e.sysex.assign(sd.begin(), sd.begin() + n2x::g_singleDumpSize);
    e.sysex.back() = 0xf7;
    return e;
}

synthLib::SMidiEvent multi_dump_event(const Patch &p, const int *mv) {
    n2x::State::SingleDump sd;
    n2x::State::createDefaultSingle(sd, 0, n2x::SingleDumpBankEditBuffer);
    for (int i = 0; i < kNumBytes; i++) { sd[6 + 2 * i] = p[i] & 0xf; sd[7 + 2 * i] = p[i] >> 4; }
    n2x::State::MultiDump md;
    n2x::State::createDefaultMulti(md, n2x::MultiDumpBankEditBuffer);
    n2x::State::copySingleToMulti(md, sd, 0);
    for (int i = 0; i < NR_NUM_MULTI; i++) n2x::State::changeDumpParameter(md, n2x::State::getOffsetInMultiDump((n2x::MultiParam)g_nr_multi[i].mp), (uint8_t)mv[i]);
    synthLib::SysexBuffer sx(md.begin(), md.end());
    sx = n2x::State::validateDump(sx);
    synthLib::SMidiEvent e(synthLib::MidiEventSource::Host);
    e.sysex = sx;
    return e;
}

void tune_thread() {
    pthread_setname_np(pthread_self(), "NRemu");
    // Gen2 big.LITTLE (Live III: A55 0-3, A76 4-7): the fast cores minus MPC's "Audio Processing" core; the device's own threads inherit the mask.
    if (!getenv("NR_NOPIN")) fastcores::pin_this_thread();
    int nice_val = 0;
    if (const char *e = getenv("NR_NICE")) nice_val = atoi(e);
    if (nice_val) setpriority(PRIO_PROCESS, (id_t)syscall(SYS_gettid), nice_val);
}

void apply_loaded(Inst *in, const Patch &p, int bank, int prog) {
    for (int i = 0; i < kNumBytes; i++) in->raw[i].store(p[i]);
    if (bank >= 0) { in->bank = bank; in->preset = prog; }
    in->bump();
}
Patch current_patch(Inst *in) {
    Patch p;
    for (int i = 0; i < kNumBytes; i++) p[i] = in->raw[i].load();
    return p;
}

std::vector<uint8_t> find_rom(const std::string &dir, std::string &name) {
    DIR *d = opendir(dir.c_str());
    if (!d) return {};
    std::vector<uint8_t> out;
    while (struct dirent *e = readdir(d)) {
        const std::string n = e->d_name;
        if (n.size() < 5 || strcasecmp(n.c_str() + n.size() - 4, ".bin")) continue;
        FILE *f = fopen((dir + "/" + n).c_str(), "rb");
        if (!f) continue;
        std::vector<uint8_t> data(kRomSize + 1);
        const size_t got = fread(data.data(), 1, data.size(), f);
        fclose(f);
        if (got != kRomSize) continue;
        data.resize(got);
        out = std::move(data);
        name = n;
        break;
    }
    closedir(d);
    return out;
}

/* the device's threads, each on a core of its own (threads that hand work to each other must not queue behind one another):
 * DSP A, DSP B and the 68331 on the first three fast cores, our own emulator thread beside the lightest of them. NR_NOSPREAD=1 skips it. */
void spread_threads() {
    const auto fast = fastcores::usable();
    if (fast.size() < 3 || getenv("NR_NOSPREAD")) return;
    DIR *d = opendir("/proc/self/task");
    if (!d) return;
    while (struct dirent *e = readdir(d)) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char path[64], comm[32] = "";
        snprintf(path, sizeof path, "/proc/self/task/%s/comm", e->d_name);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        if (!fgets(comm, sizeof comm, f)) comm[0] = 0;
        fclose(f);
        int core = -1;
        comm[strcspn(comm, "\n")] = 0;
        if (strstr(comm, "DSP A")) core = fast[0];
        else if (strstr(comm, "DSP B")) core = fast[1];
        else if (!strncmp(comm, "MC68", 4)) core = fast[2];
        if (core < 0) continue;
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(core, &set);
        if (sched_setaffinity((pid_t)atoi(e->d_name), sizeof set, &set) == 0) xlog("[emu] %s -> core %d", comm, core);
    }
    closedir(d);
}

void emu_main(Inst *in) {
    tune_thread();
    std::string rom_name;
    std::vector<uint8_t> rom = find_rom(in->dir + "/roms", rom_name);
    if (rom.empty()) {
        in->set_status("No Nord Lead 2x ROM in nodalred2x/roms/ (512k .bin)");
        in->failed = true;
        return;
    }
    { std::lock_guard<std::mutex> l(in->sm); snprintf(in->rom_name, sizeof in->rom_name, "%s", rom_name.c_str()); }
    in->set_status("Booting the Nord Lead 2x...");
    const auto t0 = std::chrono::steady_clock::now();
    std::unique_ptr<n2x::Device> dev;
    std::unique_ptr<synthLib::Plugin> plugin;
    try {
        synthLib::DeviceCreateParams p;
        p.romData = rom;
        p.romName = rom_name;
        p.hostSamplerate = (float)kRate;
        p.homePath = in->dir;
        dev.reset(new n2x::Device(p));
        if (!dev->isValid()) throw std::runtime_error("not a Nord Lead 2x ROM");
        plugin.reset(new synthLib::Plugin(dev.get(), [](synthLib::Device *d) { return d; }));
        plugin->setMidiClockEnabled(true);
        plugin->setHostSamplerate((float)kRate, 0.0f);
        plugin->setBlockSize(kBlock);
    } catch (const std::exception &e) {
        char b[96];
        snprintf(b, sizeof b, "Nord Lead start failed: %.60s", e.what());
        in->set_status(b);
        in->failed = true;
        xlog("[emu] %s", b);
        return;
    }
    xlog("[emu] device up in %.1f s", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());

    std::vector<float> zero(512, 0.0f), spare(512 * 12, 0.0f);
    float outl[512], outr[512];
    synthLib::TAudioInputs inputs = {};
    synthLib::TAudioOutputs outputs = {};
    for (auto &i : inputs) i = zero.data();
    for (size_t k = 0; k < outputs.size(); k++) outputs[k] = spare.data() + 512 * k;
    outputs[0] = outl;
    outputs[1] = outr;

    bool dirty[kNumBytes] = {}, dump_dirty = false, multi_dirty = true;
    long last_ticks = 0;
    auto last_t = std::chrono::steady_clock::now();
    uint32_t block_no = 0;
    long long boost_until = 0;

    auto send_all = [&] {           // the whole current sound and the performance values
        const Patch p = current_patch(in);
        int mv[4];
        for (int i = 0; i < 4; i++) mv[i] = in->multi[i].load();
        plugin->addMidiEvent(multi_dump_event(p, mv));
        plugin->addMidiEvent(single_dump_event(p));
    };

    auto produce = [&]() {
        std::vector<Cmd> cmds;
        { std::lock_guard<std::mutex> l(in->qm); cmds.swap(in->q); }
        for (auto &c : cmds) if (c.type == C_LOAD) { boost_until = mono_ms() + 400; break; }
        for (auto &c : cmds) {
            switch (c.type) {
            case C_MIDI:
                plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, c.m[0], c.m[1], c.m[2]));
                break;
            case C_PARAM:
                if (c.a >= 0 && c.a < kNumBytes) dirty[c.a] = true;
                break;
            case C_MULTI:
                multi_dirty = true;
                break;
            case C_LOAD:
                memset(dirty, 0, sizeof dirty);
                dump_dirty = false;
                plugin->addMidiEvent(single_dump_event(c.patch));
                break;
            case C_PANIC:
                for (uint8_t ch = 0; ch < 16; ch++) {
                    plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, (uint8_t)(0xb0 | ch), 123, 0));
                    plugin->addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, (uint8_t)(0xb0 | ch), 120, 0));
                }
                break;
            }
        }
        if (multi_dirty) {
            multi_dirty = false;
            send_all();
        }
        // parameter writes, coalesced per byte: the latest value goes out; a parameter with no controller sends the whole single
        const int8_t *cct = cc_table();
        int sent = 0;
        for (int i = 0; i < kNumBytes && sent < 8; i++) {
            if (!dirty[i]) continue;
            dirty[i] = false;
            const int v = in->raw[i].load();
            if (i == n2x::Sync) {                          // byte 52: Sync (bit 0) and Ring mod (bit 1) share a controller, Distortion has its own
                plugin->addMidiEvent(cc_event(35, v & 3));
                plugin->addMidiEvent(cc_event(80, (v >> 4) & 1));
                dump_dirty = true;                         // the controller carries only Sync; the dump makes sure Ring mod arrives
            } else if (cct[i] >= 0) plugin->addMidiEvent(cc_event(cct[i], v));
            else dump_dirty = true;
            sent++;
        }
        if (dump_dirty && !std::any_of(dirty, dirty + kNumBytes, [](bool b) { return b; })) {
            dump_dirty = false;
            plugin->addMidiEvent(single_dump_event(current_patch(in)));
        }
        {
            const double bpm = in->host_bpm.load(), ppq = in->host_ppq.load();
            const uint32_t ahead = in->wr.load(std::memory_order_relaxed) - in->rd.load(std::memory_order_relaxed);
            const bool sync = bpm > 0.0 && ppq >= 0.0 && in->ready;
            const double my_ppq = sync ? ppq + ahead * bpm / 60.0 / kRate : 0.0;
            plugin->process(inputs, outputs, kBlock, sync ? (float)bpm : 0.0f, (float)my_ppq, sync && in->host_playing.load(), sync);
        }
        block_no++;
        std::vector<synthLib::SMidiEvent> midiOut;
        plugin->getMidiOut(midiOut);                         // nothing is read back: the engine holds the sound

        const float g = in->gain.load() / 100.0f * 32767.0f;
        uint32_t w = in->wr.load(std::memory_order_relaxed);
        for (int i = 0; i < kBlock; i++) {
            in->ring[(w & (kRingFrames - 1)) * 2] = (int16_t)std::max(-32768.0f, std::min(32767.0f, outl[i] * g));
            in->ring[(w & (kRingFrames - 1)) * 2 + 1] = (int16_t)std::max(-32768.0f, std::min(32767.0f, outr[i] * g));
            w++;
        }
        in->wr.store(w, std::memory_order_release);
    };

    in->set_status("Warming up...");
    send_all();
    spread_threads();
    multi_dirty = false;
    for (int i = 0; i < kTargetFill / kBlock + 2 && !in->stop; i++) produce();
    in->ready = true;
    in->set_status("Ready - ROM loaded");
    xlog("[emu] ready after %.1f s", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());

    static const bool bench = getenv("NR_BENCH") != nullptr;
    long long rep_ms = mono_ms();
    long slow_us = 0;
    uint32_t rep_drops = in->underruns.load();
    while (!in->stop) {
        const uint32_t fill = in->wr.load(std::memory_order_relaxed) - in->rd.load(std::memory_order_acquire);
        if (bench) in->rd.store(in->wr.load());
        const uint32_t target = mono_ms() < boost_until ? (uint32_t)kBoostFill : (uint32_t)kTargetFill;
        if (!bench && (fill >= target || fill + kBlock > (uint32_t)kRingFrames)) {
            std::this_thread::sleep_for(std::chrono::microseconds(500));
            continue;
        }
        const auto c0 = std::chrono::steady_clock::now();
        produce();
        const long us = (long)std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - c0).count();
        if (us > slow_us) slow_us = us;
        if (mono_ms() - rep_ms >= 5000) {           // one line per 5 s into journalctl -u acvs when dropouts rise (EMULATOR_PORTS.md section 4)
            const uint32_t d = in->underruns.load();
            const uint32_t rmin = in->ring_min.exchange(0xffffffffu), bmax = in->burst_max.exchange(0);
            if (d != rep_drops || getenv("NR_RINGLOG"))
                fprintf(stderr, "NodalRed2x: dropouts %u (+%u), ring min %u, host burst %u, slowest chunk %ld us, emu cpu %d%%\n",
                        d, d - rep_drops, rmin == 0xffffffffu ? 0 : rmin, bmax, slow_us, in->emu_cpu.load());
            rep_drops = d; slow_us = 0; rep_ms = mono_ms();
        }
        if ((block_no % 690) == 0) {               // ~2 s
            const auto now = std::chrono::steady_clock::now();
            const long tk = emu_thread_ticks(-1);
            const double dt = std::chrono::duration<double>(now - last_t).count();
            if (dt > 0.1) in->emu_cpu = (int)((tk - last_ticks) / 100.0 / dt * 100.0);
            if (bench) xlog("[bench] %.2fx real time, emu cpu %d%%", 690.0 * kBlock / kRate / dt, in->emu_cpu.load());
            last_ticks = tk;
            last_t = now;
        }
    }
    xlog("[emu] stopping");
    plugin.reset();
    dev.reset();
}

/* ------------------------------------------------------------------ favourites: "NRFAV1\n\0", then 24 name bytes + 66 parameter bytes each */
const char kFavMagic[8] = {'N', 'R', 'F', 'A', 'V', '1', '\n', 0};
std::string fav_path(Inst *in) { return in->dir + "/favourites.dat"; }

void fav_load(Inst *in) {
    std::lock_guard<std::mutex> l(in->fm);
    in->fav_count = 0;
    FILE *f = fopen(fav_path(in).c_str(), "rb");
    if (!f) return;
    char magic[8];
    if (fread(magic, 1, 8, f) == 8 && !memcmp(magic, kFavMagic, 8)) {
        while (in->fav_count < kFavSlots && fread(in->fav_name[in->fav_count], 1, 24, f) == 24 &&
               fread(in->fav_patch[in->fav_count].data(), 1, kNumBytes, f) == (size_t)kNumBytes) {
            in->fav_name[in->fav_count][23] = 0;
            in->fav_count++;
        }
    }
    fclose(f);
}

bool fav_write(Inst *in) {            // under fm
    const std::string path = fav_path(in), tmp = path + ".tmp";
    FILE *f = fopen(tmp.c_str(), "wb");
    if (!f) return false;
    bool ok = fwrite(kFavMagic, 1, 8, f) == 8;
    for (int i = 0; ok && i < in->fav_count; i++)
        ok = fwrite(in->fav_name[i], 1, 24, f) == 24 && fwrite(in->fav_patch[i].data(), 1, kNumBytes, f) == (size_t)kNumBytes;
    ok = (fclose(f) == 0) && ok;
    return ok && rename(tmp.c_str(), path.c_str()) == 0;
}

std::string sound_name(Inst *in, int b, int p);

void fav_save(Inst *in) {
    const Patch d = current_patch(in);
    std::string nm = sound_name(in, in->bank, in->preset);
    std::lock_guard<std::mutex> l(in->fm);
    if (in->fav_count >= kFavSlots) return;
    for (int i = 0; i < in->fav_count; i++) if (in->fav_patch[i] == d) return;
    const int i = in->fav_count;
    snprintf(in->fav_name[i], 24, "%s", nm.empty() ? "Favourite" : nm.c_str());
    in->fav_patch[i] = d;
    in->fav_count++;
    if (!fav_write(in)) in->fav_count--;
    else { in->fav_current = i; in->fav_stamp = in->load_gen; }
}

void fav_delete(Inst *in) {           // only the favourite that is the current sound
    std::lock_guard<std::mutex> l(in->fm);
    const int d = in->fav_current;
    if (d < 0 || d >= in->fav_count || in->fav_stamp != in->load_gen) return;
    for (int i = d; i + 1 < in->fav_count; i++) { memcpy(in->fav_name[i], in->fav_name[i + 1], 24); in->fav_patch[i] = in->fav_patch[i + 1]; }
    in->fav_count--;
    fav_write(in);
    in->fav_current = -1;
}

void load_patch(Inst *in, const Patch &p, int bank, int prog) {
    apply_loaded(in, p, bank, prog);
    Cmd c;
    c.type = C_LOAD;
    c.patch = p;
    in->push(std::move(c));
    in->load_gen++;
}

void fav_pick(Inst *in, int idx) {
    std::lock_guard<std::mutex> l(in->fm);
    if (idx < 0 || idx >= kFavSlots) return;
    if (idx < in->fav_count) load_patch(in, in->fav_patch[idx], -1, 0);
    in->fav_current = idx;            // an empty slot shows as picked, nothing loads
    in->fav_stamp = in->load_gen;
    in->bump();
}

/* a sound's name for the lists: the file's own (Aura editor name) or its number */
std::string sound_name(Inst *in, int b, int p) {
    if (b < 0 || b >= bank_count(in) || p < 0 || p >= bank_size(in, b)) return "";
    return in->banks[b].sounds[p].name;
}

/* ------------------------------------------------------------------ the engine interface */

void *eng_create(const char *dir) {
    if (!g_log) g_log = fopen(getenv("NR_LOG") ? getenv("NR_LOG") : "/tmp/nodalred2x.log", "a");
    Inst *in = new Inst();
    in->dir = dir ? dir : "";
    const Patch def = default_patch();
    for (int i = 0; i < kNumBytes; i++) in->raw[i].store(def[i]);
    for (int i = 0; i < NR_NUM_MULTI; i++) in->multi[i].store(g_nr_multi[i].def);
    Bank st;
    st.name = "STARTERS";
    st.sounds = starters();
    in->banks.push_back(std::move(st));
    fav_load(in);
    scan_banks(in);
    in->th = std::thread(emu_main, in);
    return in;
}

void eng_destroy(void *p) {
    Inst *in = (Inst *)p;
    if (!in) return;
    in->stop = true;
    if (in->th.joinable()) in->th.join();
    delete in;
}

void select_sound(Inst *in, int bank, int prog) {
    if (in->failed) { bank = clampi(bank, 0, kMaxBanks - 1); prog = clampi(prog, 0, 127); }       // no ROM: keep what was asked
    else {
        bank = clampi(bank, 0, bank_count(in) - 1);
        prog = clampi(prog, 0, std::max(0, bank_size(in, bank) - 1));
    }
    in->bank_page = bank / NR_BANK_TILES;
    in->bank = bank;
    in->preset = prog;
    in->page = prog / NR_PATCH_TILES;
    if (bank_size(in, bank) > 0) load_patch(in, in->banks[bank].sounds[prog].p, bank, prog);
    in->bump();
}

void eng_midi(void *p, const uint8_t *msg, int len) {
    Inst *in = (Inst *)p;
    if (!in || len < 1 || len > 3 || msg[0] < 0x80 || msg[0] >= 0xf0) return;
    const uint8_t st = msg[0] & 0xf0;
    if (st == 0xc0 && len >= 2) { if (msg[1] < bank_size(in, in->bank)) select_sound(in, in->bank, msg[1]); return; }
    if (st == 0xb0 && len >= 3 && (msg[1] == 0 || msg[1] == 32)) {     // bank select: takes effect with the next program change
        if (msg[1] == 0 && msg[2] < bank_count(in)) in->bank = msg[2];
        return;
    }
    Cmd c;
    c.type = C_MIDI;
    c.m[0] = st;                                // part A listens on channel 1
    c.m[1] = len > 1 ? msg[1] : 0;
    c.m[2] = len > 2 ? msg[2] : 0;
    in->push(std::move(c));
}

int slot_key(const char *key, const char *prefix, int max, bool *on) {
    const size_t n = strlen(prefix);
    if (strncmp(key, prefix, n) != 0) return 0;
    char *end = nullptr;
    const long v = strtol(key + n, &end, 10);
    if (end == key + n || v < 1 || v > max) return 0;
    if (*end == 0) { *on = false; return (int)v; }
    if (strcmp(end, "_on") == 0) { *on = true; return (int)v; }
    return 0;
}

int pages(Inst *in) { return std::max(1, (bank_size(in, in->bank) + NR_PATCH_TILES - 1) / NR_PATCH_TILES); }
int hexval(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }

void restore_state(Inst *in, const char *s) {
    auto num = [&](const char *k, int def) {
        const char *q = strstr(s, k);
        return q ? atoi(q + strlen(k)) : def;
    };
    in->bank = clampi(num("\"bank\":", 0), 0, bank_count(in) - 1);
    in->preset = clampi(num("\"preset\":", 0), 0, std::max(0, bank_size(in, in->bank) - 1));
    in->page = in->preset / NR_PATCH_TILES;
    in->bank_page = in->bank / NR_BANK_TILES;
    in->gain = clampi(num("\"gain\":", 70), 10, 400);
    for (int i = 0; i < NR_NUM_MULTI; i++) {
        char k[32];
        snprintf(k, sizeof k, "\"%s\":", g_nr_multi[i].key);
        in->multi[i] = clampi(num(k, g_nr_multi[i].def), g_nr_multi[i].lo, g_nr_multi[i].hi);
    }
    const char *h = strstr(s, "\"single\":\"");
    if (h) {
        h += 10;
        Patch pt;
        int n = 0;
        while (n < kNumBytes && hexval(h[0]) >= 0 && hexval(h[1]) >= 0) { pt[n++] = (uint8_t)(hexval(h[0]) * 16 + hexval(h[1])); h += 2; }
        if (n == kNumBytes) {
            load_patch(in, pt, -1, 0);
            Cmd c;
            c.type = C_MULTI;
            in->push(std::move(c));
            return;
        }
    }
    select_sound(in, in->bank, in->preset);
    Cmd c;
    c.type = C_MULTI;
    in->push(std::move(c));
}

void write_byte(Inst *in, int idx, uint8_t v) {
    in->raw[idx].store(v);
    Cmd c;                                      // the emulator thread coalesces: one message per byte, latest value
    c.type = C_PARAM;
    c.a = idx;
    in->push(std::move(c));
}

void eng_set(void *p, const char *key, const char *val) {
    Inst *in = (Inst *)p;
    if (!in || !key || !val) return;
    bool on = false;
    int n;
    const bool press = atoi(val) != 0;
    if ((n = slot_key(key, "bank_slot_", NR_BANK_TILES, &on)) && !on) {
        const int b = in->bank_page * NR_BANK_TILES + n - 1;
        if (press && b < bank_count(in)) select_sound(in, b, 0);
        return;
    }
    if (!strcmp(key, "bank_page_prev")) { if (press && in->bank_page > 0) { in->bank_page--; in->bump(); } return; }
    if (!strcmp(key, "bank_page_next")) { if (press && (in->bank_page + 1) * NR_BANK_TILES < bank_count(in)) { in->bank_page++; in->bump(); } return; }
    if ((n = slot_key(key, "patch_slot_", NR_PATCH_TILES, &on)) && !on) {
        if (press && in->page * NR_PATCH_TILES + n - 1 < bank_size(in, in->bank)) select_sound(in, in->bank, in->page * NR_PATCH_TILES + n - 1);
        return;
    }
    if (!strcmp(key, "patch_page_prev")) { if (press && in->page > 0) { in->page--; in->bump(); } return; }
    if (!strcmp(key, "patch_page_next")) { if (press && in->page + 1 < pages(in)) { in->page++; in->bump(); } return; }
    if (!strcmp(key, "preset")) { select_sound(in, in->bank, atoi(val)); return; }
    if (!strcmp(key, "bank_index")) { select_sound(in, atoi(val), 0); return; }
    if (!strcmp(key, "preset_next") || !strcmp(key, "preset_prev")) {
        const int np = std::max(1, bank_size(in, in->bank));
        if (press) select_sound(in, in->bank, (in->preset + (!strcmp(key, "preset_next") ? 1 : np - 1)) % np);
        return;
    }
    if (!strcmp(key, "bank_next") || !strcmp(key, "bank_prev")) {
        const int nb = bank_count(in);
        if (press) select_sound(in, (in->bank + (!strcmp(key, "bank_next") ? 1 : nb - 1)) % nb, 0);
        return;
    }
    if (!strcmp(key, "all_notes_off")) { if (press) { Cmd c; c.type = C_PANIC; in->push(std::move(c)); } return; }
    if (!strcmp(key, "init_patch")) { if (press) select_sound(in, in->bank, in->preset); return; }      // reload the stored sound
    if (!strcmp(key, "fav_save")) { if (press) { fav_save(in); in->bump(); } return; }
    if (!strcmp(key, "fav_delete")) { if (press) { fav_delete(in); in->bump(); } return; }
    if (!strcmp(key, "favourite")) { fav_pick(in, atoi(val)); return; }
    if (!strcmp(key, "gain")) { in->gain = clampi(atoi(val), 10, 400); return; }
    if (!strcmp(key, "state")) { restore_state(in, val); return; }
    for (int i = 0; i < NR_NUM_MULTI; i++)
        if (!strcmp(key, g_nr_multi[i].key)) {
            in->multi[i] = clampi(atoi(val), g_nr_multi[i].lo, g_nr_multi[i].hi);
            Cmd c;
            c.type = C_MULTI;
            in->push(std::move(c));
            return;
        }
    auto it = np_index().find(key);
    if (it == np_index().end()) return;
    const nr_param_t &q = g_nr_params[it->second];
    write_byte(in, q.idx, field_set(q, in->raw[q.idx].load(), value_to_raw(q, atoi(val))));
}

int put(char *buf, int n, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    const int r = vsnprintf(buf, n, fmt, ap);
    va_end(ap);
    return r < 0 ? 0 : std::min(r, n - 1);
}

int eng_get(void *p, const char *key, char *buf, int n) {
    Inst *in = (Inst *)p;
    if (!in || !key || n < 2) return -1;
    bool on = false;
    int k;
    if ((k = slot_key(key, "bank_slot_", NR_BANK_TILES, &on))) {
        const int b = in->bank_page * NR_BANK_TILES + k - 1;
        if (on) return put(buf, n, "%d", b == in->bank ? 1 : 0);
        return put(buf, n, "%s", b < bank_count(in) ? in->banks[b].name.c_str() : "");
    }
    if (!strcmp(key, "bank_page_text")) return put(buf, n, "%d / %d", in->bank_page + 1, (bank_count(in) + NR_BANK_TILES - 1) / NR_BANK_TILES);
    if ((k = slot_key(key, "patch_slot_", NR_PATCH_TILES, &on))) {
        const int idx = in->page * NR_PATCH_TILES + k - 1;
        if (on) return put(buf, n, "%d", idx == in->preset ? 1 : 0);
        if (idx >= bank_size(in, in->bank)) return put(buf, n, "%s", "");
        std::lock_guard<std::mutex> l(in->sm);
        const std::string nm = sound_name(in, in->bank, idx);
        return put(buf, n, "%02d %s", idx + 1, nm.c_str());
    }
    if (!strcmp(key, "patch_page_text")) return put(buf, n, "PAGE %d / %d", in->page + 1, pages(in));
    if (!strcmp(key, "preset")) return put(buf, n, "%d", in->preset.load());
    if (!strcmp(key, "bank_index")) return put(buf, n, "%d", in->bank.load());
    if (!strcmp(key, "bank_name")) return put(buf, n, "%s", in->bank < bank_count(in) ? in->banks[in->bank].name.c_str() : "-");
    if (!strcmp(key, "preset_name")) {
        std::lock_guard<std::mutex> l(in->sm);
        const std::string nm = sound_name(in, in->bank, in->preset);
        return put(buf, n, "%02d %s", in->preset.load() + 1, nm.c_str());
    }
    if (!strcmp(key, "rom_name")) { std::lock_guard<std::mutex> l(in->sm); return put(buf, n, "%s", in->rom_name[0] ? in->rom_name : "-"); }
    if (!strcmp(key, "loading_status")) { std::lock_guard<std::mutex> l(in->sm); return put(buf, n, "%s", in->status); }
    if (!strcmp(key, "engine_stats")) {
        /* any change of a polled text makes MPC re-list its menus: hold it while the PRESET menu is in use, CPU in steps of 10 */
        std::lock_guard<std::mutex> l(in->stm);
        if (mono_ms() - in->fav_list_ms < 15000 && in->stats_cache[0]) return put(buf, n, "%s", in->stats_cache);
        const int cpu = in->emu_cpu.load();
        if (in->stats_cpu < 0 || abs(cpu - in->stats_cpu) >= 10) in->stats_cpu = cpu / 10 * 10;
        snprintf(in->stats_cache, sizeof in->stats_cache, "DROPOUTS %u   CPU %d%%", in->underruns.load(), in->stats_cpu);
        return put(buf, n, "%s", in->stats_cache);
    }
    if (!strcmp(key, "gain")) return put(buf, n, "%d", in->gain.load());
    if (!strcmp(key, "favourite")) {      // the picked favourite while it is the sound, else the first empty slot
        std::lock_guard<std::mutex> l(in->fm);
        const bool cur = in->fav_current >= 0 && in->fav_stamp == in->load_gen;
        return put(buf, n, "%d", cur ? in->fav_current : std::min(in->fav_count, kFavSlots - 1));
    }
    if (!strncmp(key, "favourite:", 10)) {
        in->fav_list_ms = mono_ms();
        std::lock_guard<std::mutex> l(in->fm);
        const int i = atoi(key + 10);
        return put(buf, n, "%s", i >= 0 && i < in->fav_count ? in->fav_name[i] : "-");
    }
    if (!strcmp(key, "fav_text")) { std::lock_guard<std::mutex> l(in->fm); return put(buf, n, "FAVOURITES %d / %d", in->fav_count, kFavSlots); }
    if (!strcmp(key, "display_rev")) return put(buf, n, "%u", in->rev.load());
    if (!strcmp(key, "state")) {
        int off = put(buf, n, "{\"state_version\":1,\"bank\":%d,\"preset\":%d,\"gain\":%d", in->bank.load(), in->preset.load(), in->gain.load());
        for (int i = 0; i < NR_NUM_MULTI; i++) off += put(buf + off, n - off, ",\"%s\":%d", g_nr_multi[i].key, in->multi[i].load());
        if (off + kNumBytes * 2 + 16 < n) {
            off += put(buf + off, n - off, ",\"single\":\"");
            static const char hx[] = "0123456789abcdef";
            for (int i = 0; i < kNumBytes; i++) { const uint8_t b = in->raw[i].load(); buf[off++] = hx[b >> 4]; buf[off++] = hx[b & 15]; }
            buf[off] = 0;
            off += put(buf + off, n - off, "\"");
        }
        off += put(buf + off, n - off, "}");
        return off;
    }
    for (int i = 0; i < NR_NUM_MULTI; i++)
        if (!strcmp(key, g_nr_multi[i].key)) return put(buf, n, "%d", in->multi[i].load());
    auto it = np_index().find(key);
    if (it != np_index().end()) {
        const nr_param_t &q = g_nr_params[it->second];
        return put(buf, n, "%d", raw_to_value(q, field_get(q, in->raw[q.idx].load())));
    }
    return -1;
}

void eng_render(void *p, int16_t *out, int frames) {
    Inst *in = (Inst *)p;
    if (!in || !in->ready.load(std::memory_order_acquire)) { memset(out, 0, (size_t)frames * 4); return; }
    uint32_t r = in->rd.load(std::memory_order_relaxed);
    const uint32_t avail = in->wr.load(std::memory_order_acquire) - r;
    if (avail < in->ring_min.load(std::memory_order_relaxed)) in->ring_min.store(avail, std::memory_order_relaxed);
    if ((uint32_t)frames > in->burst_max.load(std::memory_order_relaxed)) in->burst_max.store((uint32_t)frames, std::memory_order_relaxed);
    const int got = (int)std::min<uint32_t>(avail, (uint32_t)frames);
    for (int i = 0; i < got; i++, r++) {
        out[i * 2] = in->ring[(r & (kRingFrames - 1)) * 2];
        out[i * 2 + 1] = in->ring[(r & (kRingFrames - 1)) * 2 + 1];
    }
    in->rd.store(r, std::memory_order_release);
    if (got < frames) {
        memset(out + got * 2, 0, (size_t)(frames - got) * 4);
        in->underruns.fetch_add(1, std::memory_order_relaxed);
    }
}

void eng_song_pos(void *p, double ppq, double bpm, int playing, int frames) {
    (void)frames;
    Inst *in = (Inst *)p;
    if (!in) return;
    in->host_ppq = ppq;
    in->host_bpm = bpm;
    in->host_playing = playing != 0;
}

const mpc_engine_t engine = {eng_create, eng_destroy, eng_midi, eng_set, eng_get, eng_render, nullptr, eng_song_pos};

}  // namespace

extern "C" const mpc_engine_t *mpc_engine(void) { return &engine; }
