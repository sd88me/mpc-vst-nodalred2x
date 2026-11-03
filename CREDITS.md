# Credits and licences

NodalRed2x for MPC stands on the work of others. Each licence applies to its own part; the plugin as a whole is **GPL-3.0** (`LICENSE`).

- **[gearmulator](https://github.com/dsp56300/gearmulator)** by Dieter Mueller (dsp56300) and contributors, **GPL-3.0**: the Clavia Nord Lead 2x emulation
  (`n2xLib`: the instrument's 68331 firmware host and its two DSP56362 voice DSPs) and the support libraries (`synthLib`, `baseLib`, `hardwareLib`).
  "NodalRed2x" is gearmulator's name for its Nord Lead 2x plugin. Vendored from the
  [charlesvestal/gearmulator](https://github.com/charlesvestal/gearmulator) snapshot that Xenia and Vavra for MPC use.
- **[dsp56300](https://github.com/dsp56300/dsp56300)** (the DSP56300 emulator and its JIT: `dsp56kEmu`, `dsp56kBase`) and **[mc68k](https://github.com/dsp56300/mc68k)**
  (on Musashi), **GPL-3.0**; **[AsmJit](https://github.com/asmjit/asmjit)**, **zlib**; **libresample**, BSD / LGPL.
- **The "n2xTrancy" skin of gearmulator's NodalRed2x by theusualsuspects**, **GPL-3.0**: the red background and the "NODAL RED 2X" lettering, the big knob
  filmstrip and the panel look (`skin/n2xTrancy/`), and gearmulator's Nord Lead 2x parameter table (`skin/parameterDescriptions_n2x.json`).
- **Liberation Sans** (Red Hat / Google, **SIL OFL 1.1**) for the page text and live text (`vst/fonts/`).
- **[mpc-vst-plugins](https://github.com/open-mpc/mpc-vst-plugins)**: the plugin wrapper (`wrapper/vst2_wrap.c`), `fast_cores.h` and the skin tools.

NodalRed2x for MPC is an independent project, not affiliated with or endorsed by Clavia or Nord Keyboards. "Nord Lead" is the name of the instrument it emulates.
No ROM is included, and none may be shared.
