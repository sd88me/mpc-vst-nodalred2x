#include <cmath>
#include <dirent.h>
#include <thread>
#include <cstring>
// Boot the Nord Lead 2x ROM and render N seconds with a held chord; prints realtime factor.
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include "n2xLib/n2xdevice.h"
#include "synthLib/plugin.h"
static void thread_report(double secs) {      // CPU% per thread name over the run
    DIR *d = opendir("/proc/self/task"); if (!d) return;
    while (struct dirent *e = readdir(d)) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char p[96], comm[32] = "", line[512]; snprintf(p, sizeof p, "/proc/self/task/%s/comm", e->d_name);
        FILE *f = fopen(p, "r"); if (!f) continue; if (!fgets(comm, sizeof comm, f)) comm[0] = 0; fclose(f); comm[strcspn(comm, "\n")] = 0;
        snprintf(p, sizeof p, "/proc/self/task/%s/stat", e->d_name); f = fopen(p, "r"); if (!f) continue;
        unsigned long ut = 0, st = 0;
        if (fgets(line, sizeof line, f)) { const char *q = strrchr(line, ')'); if (q) sscanf(q + 2, "%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu", &ut, &st); }
        fclose(f);
        if (ut + st > 10) printf("  %-12s %5.1f%%\n", comm, (ut + st) / 100.0 / secs * 100.0);
    }
    closedir(d);
}
static int g_ch = 0x90;
static int b_ch(){return g_ch;}
int main(int argc, char **argv) {
    std::ifstream f(argv[1], std::ios::binary);
    std::vector<uint8_t> rom((std::istreambuf_iterator<char>(f)), {});
    double secs = argc > 2 ? atof(argv[2]) : 10;
    synthLib::DeviceCreateParams p; p.romData = rom; p.romName = "nord_lead_2x.bin"; p.hostSamplerate = 48000; p.homePath = "/tmp";
    auto t0 = std::chrono::steady_clock::now();
    n2x::Device dev(p);
    printf("valid=%d boot %.2fs sr=%.0f out=%u\n", dev.isValid(), std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count(), dev.getSamplerate(), dev.getChannelCountOut());
    if (argc > 3) printf("clock %d%% ok=%d hz=%llu\n", atoi(argv[3]), dev.setDspClockPercent(atoi(argv[3])), (unsigned long long)dev.getDspClockHz());
    synthLib::Plugin plugin(&dev, [](synthLib::Device *d) { return d; });
    plugin.setHostSamplerate(48000, 0); plugin.setBlockSize(64);
    std::vector<float> z(64, 0), o(64 * 12, 0);
    synthLib::TAudioInputs in = {}; synthLib::TAudioOutputs out = {};
    for (auto &i : in) i = z.data();
    for (size_t k = 0; k < out.size(); k++) out[k] = o.data() + 64 * k;
    std::vector<synthLib::SMidiEvent> mi, mo;
    std::vector<int> notes = {48, 55, 60, 64, 67};
    if (getenv("HEAVY")) notes = {36, 43, 48, 52, 55, 60, 64, 67, 71, 74, 79, 84};
    if (getenv("HEAVY")) { mi.push_back(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0xb0, 16, 127)); mi.push_back(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0xb0, 15, 127)); }
    for (int n : notes) { synthLib::SMidiEvent e(synthLib::MidiEventSource::Host, b_ch(), n, 100); mi.push_back(e); }
    auto t1 = std::chrono::steady_clock::now();
    long blocks = (long)(secs * 48000 / 64); double peak = 0, pk[4] = {0,0,0,0}; unsigned long long h = 1469598103934665603ull; double sq = 0; long sn = 0;
    for (long b = 0; b < blocks; b++) {
        plugin.process(in, out, 64, 120.0f, 0.0f, false, false);
        (void)mo;
        for (int i = 0; i < 64; i++) for (size_t k = 0; k < 2; k++) { if (b > blocks / 2) { sq += out[k][i] * out[k][i]; sn++; } int v = (int)(out[k][i] * 32767); h = (h ^ (unsigned)v) * 1099511628211ull; }
        for (int i = 0; i < 64; i++) for (size_t k = 0; k < 4; k++) pk[k] = std::max(pk[k], (double)std::abs(out[k][i]));
        if (b % 1500 == 1499) { printf("t=%.1f pk %.3f %.3f %.3f %.3f\n", b*64/48000.0, pk[0], pk[1], pk[2], pk[3]); pk[0]=pk[1]=pk[2]=pk[3]=0; }
        if (getenv("PACED")) std::this_thread::sleep_until(t1 + std::chrono::microseconds((long)((b + 1) * 64 * 1e6 / 48000)));
        if (b == 0 || b == 4000) for (auto &e : mi) plugin.addMidiEvent(e);
    }
    double dt = std::chrono::duration<double>(std::chrono::steady_clock::now() - t1).count();
    if (getenv("PACED")) thread_report(dt);
    printf("rendered %.1fs in %.2fs = %.2f of realtime, rms2 %.4f\n", secs, dt, dt / secs, sqrt(sq / (sn ? sn : 1)));
}
