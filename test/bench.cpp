// Boot the Nord Lead 2x ROM and render N seconds with a held chord; prints realtime factor.
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include "n2xLib/n2xdevice.h"
#include "synthLib/plugin.h"
int main(int argc, char **argv) {
    std::ifstream f(argv[1], std::ios::binary);
    std::vector<uint8_t> rom((std::istreambuf_iterator<char>(f)), {});
    double secs = argc > 2 ? atof(argv[2]) : 10;
    synthLib::DeviceCreateParams p; p.romData = rom; p.romName = "nord_lead_2x.bin"; p.hostSamplerate = 48000; p.homePath = "/tmp";
    auto t0 = std::chrono::steady_clock::now();
    n2x::Device dev(p);
    printf("valid=%d boot %.2fs sr=%.0f out=%u\n", dev.isValid(), std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count(), dev.getSamplerate(), dev.getChannelCountOut());
    synthLib::Plugin plugin(&dev, [](synthLib::Device *d) { return d; });
    plugin.setHostSamplerate(48000, 0); plugin.setBlockSize(64);
    std::vector<float> z(64, 0), o(64 * 12, 0);
    synthLib::TAudioInputs in = {}; synthLib::TAudioOutputs out = {};
    for (auto &i : in) i = z.data();
    for (size_t k = 0; k < out.size(); k++) out[k] = o.data() + 64 * k;
    std::vector<synthLib::SMidiEvent> mi, mo;
    for (int n : {48, 55, 60, 64, 67}) { synthLib::SMidiEvent e(synthLib::MidiEventSource::Host, 0x90, n, 100); mi.push_back(e); }
    auto t1 = std::chrono::steady_clock::now();
    long blocks = (long)(secs * 48000 / 64); double peak = 0;
    for (long b = 0; b < blocks; b++) {
        plugin.process(in, out, 64, 120.0f, 0.0f, false, false);
        (void)mo;
        for (int i = 0; i < 64; i++) for (size_t k = 0; k < 2; k++) peak = std::max(peak, (double)std::abs(out[k][i]));
        if (b == 0) for (auto &e : mi) plugin.addMidiEvent(e);
    }
    double dt = std::chrono::duration<double>(std::chrono::steady_clock::now() - t1).count();
    printf("rendered %.1fs in %.2fs = %.2f of realtime, peak %.3f\n", secs, dt, dt / secs, peak);
}
