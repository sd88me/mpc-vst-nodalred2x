// Create, play a little and destroy an n2x::Device over and over: finds teardown races. usage: lifecycle <rom.bin> [rounds]
#include <cstdio>
#include <execinfo.h>
#include <signal.h>
#include <unistd.h>
#include <fstream>
#include <iterator>
#include "n2xLib/n2xdevice.h"
#include "synthLib/plugin.h"
static void onsegv(int sig, siginfo_t *si, void *) {
    void *bt[40]; int n = backtrace(bt, 40);
    dprintf(2, "SIGNAL %d addr %p\n", sig, si->si_addr);
    backtrace_symbols_fd(bt, n, 2);
    _exit(139);
}
static int maps() { FILE *f = fopen("/proc/self/maps", "r"); int n = 0, c; while ((c = fgetc(f)) != EOF) if (c == 10) n++; fclose(f); return n; }
int main(int argc, char **argv) {
    if (!getenv("NOSIGH")) { struct sigaction sa = {}; sa.sa_sigaction = onsegv; sa.sa_flags = SA_SIGINFO; sigaction(SIGSEGV, &sa, nullptr); sigaction(SIGABRT, &sa, nullptr); }
    std::ifstream f(argv[1], std::ios::binary);
    std::vector<uint8_t> rom((std::istreambuf_iterator<char>(f)), {});
    const int rounds = argc > 2 ? atoi(argv[2]) : 10;
    for (int r = 0; r < rounds; r++) {
        synthLib::DeviceCreateParams p; p.romData = rom; p.romName = "nord_lead_2x.bin"; p.hostSamplerate = 44100; p.homePath = "/tmp";
        {
            n2x::Device dev(p);
            synthLib::Plugin plugin(&dev, [](synthLib::Device *d) { return d; });
            plugin.setHostSamplerate(44100, 0); plugin.setBlockSize(128);
            std::vector<float> z(128, 0), o(128 * 12, 0);
            synthLib::TAudioInputs in = {}; synthLib::TAudioOutputs out = {};
            for (auto &i : in) i = z.data();
            for (size_t k = 0; k < out.size(); k++) out[k] = o.data() + 128 * k;
            plugin.addMidiEvent(synthLib::SMidiEvent(synthLib::MidiEventSource::Host, 0x90, 60, 100));
            for (int b = 0; b < 100; b++) plugin.process(in, out, 128, 0, 0, false, false);
            printf("round %d maps %d\n", r, maps()); fflush(stdout);
        }
        printf("round %d ok\n", r); fflush(stdout);
    }
}
