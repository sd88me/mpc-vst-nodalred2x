# Vendored source
- `gearmulator/` (framework/{baseLib,synthLib,hardwareLib}, 3rdparty/libresample, cpu/mc68k, cpu/dsp56300/*, claudia/n2x/n2xLib): from
  https://github.com/charlesvestal/gearmulator commit `69981792efa44114aaafda91bed69faa4c96fc64` (same snapshot as Xenia/Vavra for MPC). GPL-3.0.
- Local patches: `n2xdsp.cpp` includes dsp56kDebugger only `#if DSP56300_DEBUGGER`; `cpu/mc68k/logging.h` makes MCLOG a no-op unless MCLOG_ENABLED.
- `src/dsp/fast_cores.h`: mpc-vst-plugins `wrapper/fast_cores.h`.
