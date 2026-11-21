# VELMARA — The Poster for a Place That Isn't There

[![make.fun bounty](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539)
[![rank](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/zammili/poster-for-a-place-that-isnt-there/rank.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539#leaderboard)
[![reward](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/zammili/poster-for-a-place-that-isnt-there/reward.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539?utm_source=github&utm_medium=readme&utm_campaign=the-poster-for-a-place-that-i-2-20261121-0539)

**VELMARA — where the sun sets twice.**

Velmara is an island that does not exist: a twin-peaked isle whose notch
catches the sun on its way down, so the light dies once behind the west
peak, flares back for one held breath in the gap, and sets a second time
into the sea. A striped lighthouse keeps the east peak, a single boat
sails the sun's road home, and the whole poster is printed — in code —
like a vintage screen-print: flat inks, banded dusk sky, misregistered
lettering and a honest grain over everything.

## Run it

```sh
python3 main.py
```

Writes the poster to `/output/entry.png` (768 × 1024, indexed PNG,
well under the 1 MiB gate). No network, no dependencies — Python 3.13
standard library only.

## How it is made

Everything is hand-rolled in `main.py`:

- a small span-based rasteriser (rects, circles, scanline polygons,
  alpha-blended wedges, capsule strokes) painting at 2× supersampling;
- a hand-drawn single-stroke lettering set on a 10 × 14 grid, set with
  a coral misregistration shadow in the manner of cheap travel posters;
- a fixed screen-print palette (teal dusk, peach horizon, gold sun,
  coral accent) with Bayer ordered dithering that doubles as the
  print grain, plus a gentle vignette;
- a from-scratch indexed-PNG encoder (`struct` + `zlib`) with
  per-row filter selection.

The scene is deterministic: same code, same poster, every run.

## License

MIT — see [LICENSE](LICENSE).

---

Entered on make.fun with referral ref nj55s4jw and campaign slug the-poster-for-a-place-that-i-2-20261121-0539.
