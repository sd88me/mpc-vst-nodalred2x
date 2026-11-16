# NodalRed2x 0.2.0

NodalRed2x gets a new native MPC screen in the look of the original skin, laid out like the Nord Lead 2x panel, with RANDOM and named favourites.

## What's new
- **A new screen, 5 pages** (MAIN, BANKS, OSC/FILTER, AMP/MOD, MORPH): the original skin's red, charcoal and slate, knobs on lilac scales with the
  envelope stages pictured over the ADSR knobs, choices as green LEDs you tap, each with a cycle button that steps through them as on the real
  panel, and on/off switches with their LED.
- **RANDOM**: a random sound from every loaded bank.
- **Named favourites**: **+FAV** opens an on-screen keyboard with the sound's name (up to 20 characters); edit it and SAVE. Favourites are in
  MPC's PRESET list.
- **BANKS**: the selected bank and sound stay lit; the page steppers sit in the section headers.
- **Cleaner output**: audio reaches the MPC in floating point, so loud sounds no longer clip in the plugin.
- **Projects saved with 0.1.0 still load** with their sound and edits; the parameter order is unchanged, so automation and Q-Links carry over.

## Install
- `NodalRed2x-0.2.0-mpc-sdk.zip`: copy the folder `sd88me - VST - NodalRed2x` into a `VST2 Plugins` folder on a drive of the MPC and put your
  ROM in its `nodalred2x/roms/` (sound sets in `nodalred2x/banks/`). Needs MPC OS 3.10.1 or later, with Preferences → Enhancements (Beta) →
  Enable Enhancements and External Plugin Support switched on. Copying it over a 0.1.0 folder from the VST2-Plugins zip keeps using the ROM,
  banks and favourites in its `VST/nodalred2x/`.
- `NodalRed2x-0.2.0-mpc-aarch64.zip`: run `install.sh` on the device as root (or use the Plugin Manager). A 0.1.0 install is upgraded in place;
  your ROM, sound sets and favourites are kept.

Use one of the two, not both. 64-bit MPCs only (Live III and others); the Force and the 32-bit MPCs are not supported.
Your own Nord Lead 2x ROM is required and not included.

## Notes
- Tested on an MPC Live III as the identical beta build. A 0.1.0 project was tested offline with a real 0.1.0 project chunk; loading one on the
  device, save/reload on the device and the install.sh upgrade were not tried.
- The heaviest synth of the family: keep an eye on the DROPOUTS readout with big chords.
