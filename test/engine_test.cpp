// Engine-level test through the interface the wrapper uses (mpc_engine): boots the Nord Lead 2x ROM found in <dir>/roms, plays notes,
// changes bank and preset, moves parameters, checks the state chunk round trip.
// usage: nodalred2x_engine_test <data dir with roms/> [seconds of audio per phase] [wav out]
extern "C" {
#include "engine.h"
}
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

static int fails = 0;
#define CHECK(c, ...) do { if (c) printf("ok   " __VA_ARGS__); else { printf("FAIL " __VA_ARGS__); fails++; } printf("\n"); } while (0)
static std::vector<int16_t> g_wav;

static std::string get(const mpc_engine_t *e, void *i, const char *k) {
    char b[8192] = {0};
    if (e->get_param(i, k, b, sizeof b) <= 0) return "";
    return b;
}

static double render_rms(const mpc_engine_t *e, void *i, double secs, double *peak = nullptr) {
    int16_t buf[256];
    double sq = 0, pk = 0; long n = 0;
    const int blocks = (int)(secs * 44100 / 128);
    auto t0 = std::chrono::steady_clock::now();
    for (int b = 0; b < blocks; b++) {
        e->render(i, buf, 128);
        g_wav.insert(g_wav.end(), buf, buf + 256);
        for (int k = 0; k < 256; k++) { double v = buf[k] / 32768.0; sq += v * v; if (fabs(v) > pk) pk = fabs(v); n++; }
        std::this_thread::sleep_until(t0 + std::chrono::microseconds((long)((b + 1) * 128 * 1e6 / 44100)));
    }
    if (peak) *peak = pk;
    return sqrt(sq / n);
}

static bool wait_ready(const mpc_engine_t *e, void *i, int seconds) {
    for (int w = 0; w < seconds * 10; w++) {
        const std::string s = get(e, i, "loading_status");
        if (s.rfind("Ready", 0) == 0) return true;
        if (s.rfind("No ", 0) == 0 || s.find("fail") != std::string::npos || s.find("did not") != std::string::npos) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return false;
}

static void write_wav(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    const uint32_t data = (uint32_t)g_wav.size() * 2, rate = 44100, br = rate * 4, sz = 36 + data;
    const uint16_t fmt = 1, ch = 2, ba = 4, bits = 16;
    const uint32_t fsz = 16;
    fwrite("RIFF", 1, 4, f); fwrite(&sz, 4, 1, f); fwrite("WAVEfmt ", 1, 8, f); fwrite(&fsz, 4, 1, f);
    fwrite(&fmt, 2, 1, f); fwrite(&ch, 2, 1, f); fwrite(&rate, 4, 1, f); fwrite(&br, 4, 1, f); fwrite(&ba, 2, 1, f); fwrite(&bits, 2, 1, f);
    fwrite("data", 1, 4, f); fwrite(&data, 4, 1, f); fwrite(g_wav.data(), 2, g_wav.size(), f);
    fclose(f);
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <data dir> [seconds] [out.wav]\n", argv[0]); return 2; }
    const double secs = argc > 2 ? atof(argv[2]) : 1.5;
    const mpc_engine_t *e = mpc_engine();
    void *i = e->create(argv[1]);
    CHECK(i != nullptr, "create");
    auto t0 = std::chrono::steady_clock::now();
    const bool up = wait_ready(e, i, 120);
    printf("boot took %.1f s: ROM %s, status \"%s\"\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count(),
           get(e, i, "rom_name").c_str(), get(e, i, "loading_status").c_str());
    CHECK(up, "boot finished");
    if (!up) { e->destroy(i); printf("FAILED\n"); return 1; }
    render_rms(e, i, 0.5);
    printf("bank \"%s\" preset \"%s\" tile2 \"%s\"\n", get(e, i, "bank_name").c_str(), get(e, i, "preset_name").c_str(), get(e, i, "patch_slot_2").c_str());

    double pk = 0;
    uint8_t on[3] = {0x90, 60, 100}, off[3] = {0x80, 60, 0};
    e->midi(i, on, 3);
    double rms = render_rms(e, i, secs, &pk);
    CHECK(rms > 0.0005, "INIT note 60 -> rms %.4f peak %.3f", rms, pk);
    e->midi(i, off, 3);
    render_rms(e, i, 1.0);
    printf("stats: %s\n", get(e, i, "engine_stats").c_str());

    // a starter sound, then cutoff (a controller) and a morph amount (a single dump)
    e->set_param(i, "preset", "2");
    render_rms(e, i, 0.5);
    CHECK(get(e, i, "preset") == "2" && get(e, i, "preset_name").find("PULSE BASS") != std::string::npos, "preset 2 -> \"%s\"", get(e, i, "preset_name").c_str());
    CHECK(get(e, i, "Cutoff") == "40" && get(e, i, "VoiceMode") == "0", "starter values: Cutoff %s VoiceMode %s", get(e, i, "Cutoff").c_str(), get(e, i, "VoiceMode").c_str());
    e->midi(i, on, 3);
    double dark = 0, open = 0;
    e->set_param(i, "Cutoff", "0"); dark = render_rms(e, i, secs);
    e->set_param(i, "Cutoff", "127"); open = render_rms(e, i, secs);
    e->midi(i, off, 3);
    CHECK(fabs(dark - open) > 1e-3, "cutoff 0 rms %.4f, cutoff 127 rms %.4f", dark, open);
    e->set_param(i, "CutoffSens", "-50");
    render_rms(e, i, 0.3);
    CHECK(get(e, i, "CutoffSens") == "-50", "CutoffSens %s", get(e, i, "CutoffSens").c_str());
    e->set_param(i, "O1Waveform", "3");
    e->set_param(i, "RingMod", "1");
    e->set_param(i, "lfo2_sync", "5");
    render_rms(e, i, 0.3);
    CHECK(get(e, i, "O1Waveform") == "3" && get(e, i, "RingMod") == "1" && get(e, i, "Sync") == "0" && get(e, i, "lfo2_sync") == "5",
          "waveform %s ring %s sync %s lfo2_sync %s", get(e, i, "O1Waveform").c_str(), get(e, i, "RingMod").c_str(), get(e, i, "Sync").c_str(), get(e, i, "lfo2_sync").c_str());
    e->midi(i, on, 3);
    rms = render_rms(e, i, secs, &pk);
    e->midi(i, off, 3);
    CHECK(rms > 0.0005, "edited sound note -> rms %.4f peak %.3f", rms, pk);

    // arpeggiator (LFO 2 / Arp = Arp Up) clocked by MPC's transport at 120 BPM
    e->set_param(i, "Lfo2Dest", "1");
    e->set_param(i, "lfo2_sync", "7");
    if (e->song_pos) for (int k = 0; k < 10; k++) e->song_pos(i, k * 0.0116, 120.0, 1, 128);
    uint8_t c2[3] = {0x90, 64, 100}, c3[3] = {0x90, 67, 100};
    e->midi(i, on, 3); e->midi(i, c2, 3); e->midi(i, c3, 3);
    rms = render_rms(e, i, 2 * secs, &pk);
    CHECK(rms > 0.0005, "arp chord with transport running -> rms %.4f peak %.3f", rms, pk);
    uint8_t alloff[3] = {0xb0, 123, 0};
    e->midi(i, alloff, 3);
    if (e->song_pos) e->song_pos(i, -1, 0, 0, 128);
    e->set_param(i, "Lfo2Dest", "3");

    // file banks
    printf("bank page \"%s\", bank tile 2 \"%s\"\n", get(e, i, "bank_page_text").c_str(), get(e, i, "bank_slot_2").c_str());
    if (!get(e, i, "bank_slot_2").empty()) {
        e->set_param(i, "bank_index", "1");
        render_rms(e, i, 0.5);
        printf("file bank \"%s\" sound \"%s\"\n", get(e, i, "bank_name").c_str(), get(e, i, "preset_name").c_str());
        e->midi(i, on, 3);
        rms = render_rms(e, i, secs, &pk);
        e->midi(i, off, 3);
        CHECK(rms > 0.0005, "file bank note -> rms %.4f peak %.3f", rms, pk);
    }

    // state round trip into a second instance
    e->set_param(i, "bank_index", "0");
    e->set_param(i, "preset", "4");
    render_rms(e, i, 0.5);
    e->set_param(i, "Resonance", "99");
    e->set_param(i, "bend_range", "5");
    render_rms(e, i, 0.3);
    const std::string st = get(e, i, "state");
    CHECK(st.find("\"single\":\"") != std::string::npos && st.size() < 4000, "state %zu bytes", st.size());
    e->destroy(i);
    void *j = e->create(argv[1]);
    e->set_param(j, "state", st.c_str());
    CHECK(wait_ready(e, j, 120), "second instance boots");
    render_rms(e, j, 1.0);
    CHECK(get(e, j, "Resonance") == "99" && get(e, j, "preset") == "4" && get(e, j, "bend_range") == "5", "restored: preset %s resonance %s bend %s",
          get(e, j, "preset").c_str(), get(e, j, "Resonance").c_str(), get(e, j, "bend_range").c_str());
    e->midi(j, on, 3);
    rms = render_rms(e, j, secs, &pk);
    e->midi(j, off, 3);
    CHECK(rms > 0.0005, "restored note -> rms %.4f peak %.3f", rms, pk);
    printf("stats: %s\n", get(e, j, "engine_stats").c_str());
    e->destroy(j);
    if (argc > 3) write_wav(argv[3]);
    printf(fails ? "FAILED (%d)\n" : "PASSED\n", fails);
    return fails ? 1 : 0;
}
