// Where do the Nord Lead 2x emulator threads spend their running time? Paced (real time) with a heavy chord, a sampler thread reads
// DSP A/B and 68331 program counters ~20k times a second, counting only samples where that thread is running (state R, not blocked).
// usage: profile <rom.bin> [seconds]
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <iterator>
#include <map>
#include <thread>
#include <vector>
#include <algorithm>
#include "n2xLib/n2xhardware.h"
#include "dsp56kEmu/disasm.h"
#include "dsp56kEmu/opcodes.h"

static int tid_of(const char *want) {
    DIR *d = opendir("/proc/self/task"); int r = -1;
    while (struct dirent *e = readdir(d)) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char p[96], c[32] = ""; snprintf(p, sizeof p, "/proc/self/task/%s/comm", e->d_name);
        FILE *f = fopen(p, "r"); if (!f) continue; if (fgets(c, sizeof c, f)) c[strcspn(c, "\n")] = 0; fclose(f);
        if (!strcmp(c, want)) r = atoi(e->d_name);
    }
    closedir(d); return r;
}
static char state_of(int tid) {
    char p[96], l[512]; snprintf(p, sizeof p, "/proc/self/task/%d/stat", tid);
    FILE *f = fopen(p, "r"); if (!f) return '?'; char s = '?';
    if (fgets(l, sizeof l, f)) { const char *q = strrchr(l, ')'); if (q) s = q[2]; } fclose(f); return s;
}

int main(int argc, char **argv) {
    std::ifstream f(argv[1], std::ios::binary);
    std::vector<uint8_t> rom((std::istreambuf_iterator<char>(f)), {});
    const double secs = argc > 2 ? atof(argv[2]) : 20;
    n2x::Hardware hw(rom, "nord_lead_2x.bin");
    if (!hw.isValid()) { printf("bad rom\n"); return 1; }
    for (int n : {36, 43, 48, 52, 55, 60, 64, 67, 71, 74, 79, 84}) hw.sendMidi(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0x90, (uint8_t)n, 110));
    hw.sendMidi(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0xb0, 16, 127));
    std::atomic<bool> stop{false};
    const int ta = tid_of("DSP DSP A"), tb = tid_of("DSP DSP B"), tu = tid_of("MC68331");
    printf("tids A %d B %d uc %d\n", ta, tb, tu);
    std::map<uint32_t, long> ha, hb, hu; long run[3] = {0, 0, 0}, tot = 0;
    std::thread smp([&] {
        while (!stop) {
            tot++;
            if (state_of(ta) == 'R') { run[0]++; ha[hw.getDSPA().dsp().getPC().toWord()]++; }
            if (state_of(tb) == 'R') { run[1]++; hb[hw.getDSPB().dsp().getPC().toWord()]++; }
            if (state_of(tu) == 'R') { run[2]++; hu[hw.getUC().getPC()]++; }
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
    });
    const uint32_t blk = 98;   // ~1 ms of 98.2 kHz
    auto t0 = std::chrono::steady_clock::now();
    for (long b = 0; b < (long)(secs * 1000); b++) {
        hw.processAudio(blk, blk);
        std::this_thread::sleep_until(t0 + std::chrono::microseconds((b + 1) * 998));
    }
    stop = true; smp.join();
    printf("samples %ld, running: DSP A %.0f%%  DSP B %.0f%%  68331 %.0f%%\n", tot, 100.0 * run[0] / tot, 100.0 * run[1] / tot, 100.0 * run[2] / tot);
    for (auto *d : {&hw.getDSPA().dsp(), &hw.getDSPB().dsp()})
        for (uint32_t a : {0x2b0u, 0x2b1u, 0x2b2u, 0x2ccu, 0x2cdu, 0x2ceu}) printf("P[%03x]=%06x ", a, d->memory().get(dsp56k::MemArea_P, a));
    printf("\n");
    dsp56k::Opcodes ops; dsp56k::Disassembler dis(ops);
    auto dump = [&](const char *name, std::map<uint32_t, long> &h, long n, dsp56k::DSP *d) {
        std::vector<std::pair<long, uint32_t>> v; for (auto &kv : h) v.push_back({kv.second, kv.first});
        std::sort(v.rbegin(), v.rend());
        printf("\n== %s: top PCs (share of its running samples)\n", name);
        for (size_t i = 0; i < v.size() && i < 12; i++) {
            printf("%6.2f%%  pc %06x", 100.0 * v[i].first / n, v[i].second);
            if (d) {
                std::string s; dsp56k::TWord a, bb; uint32_t pc = v[i].second;
                for (int k = 0; k < 6; k++) { d->memory().getOpcode(pc, a, bb); s.clear(); uint32_t len = dis.disassemble(s, a, bb, 0, 0, pc); printf("%s  [%06x %s]", k ? "" : "", pc, s.c_str()); pc += len ? len : 1; }
            } else { char buf[128] = ""; hw.getUC().disassemble(v[i].second, buf); printf("  %s", buf); }
            printf("\n");
        }
    };
    dump("DSP A", ha, run[0], &hw.getDSPA().dsp());
    dump("DSP B", hb, run[1], &hw.getDSPB().dsp());
    dump("68331", hu, run[2], nullptr);
}
