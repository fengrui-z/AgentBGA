# Third-party notices

## Carcassonne mechanical tile catalog

`src/agentbga/carcassonne/catalog.py` is an original mechanical transcription of
the 24 base tile types (72 physical tiles) from the publisher's
[English Big Box rulebook](https://cdn.svc.asmodee.net/production-zman/uploads/2024/10/Carcassonne-Big-Box-Rulebook.pdf),
page 22. Only terrain connectivity, quantities, and scoring symbols are encoded.
The implementation and SVG tile diagrams are original; no publisher artwork or
rulebook text is bundled. Carcassonne is designed by Klaus-Jürgen Wrede and
published by Hans im Glück / Z-Man Games. This implementation is unaffiliated.

## Rinascimento Framework game data

The development-card costs and noble requirements in `src/agentbga/splendor.py`
are derived from the `assets/default` research data in
[Rinascimento Framework](https://github.com/ivanbravi/RinascimentoFramework),
Copyright (c) 2021 Ivan Bravi, used under the MIT License:

> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in
> the Software without restriction, including without limitation the rights to
> use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
> the Software, and to permit persons to whom the Software is furnished to do so,
> subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
> FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
> COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
> IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
> CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Splendor is a trademark of its respective owner. AgentBGA is an independent
research project and is not affiliated with or endorsed by Space Cowboys,
Asmodee, or Board Game Arena.

## Harmonies mechanical card data

`src/agentbga/data/harmonies-cards.json` converts the numeric scores and habitat
patterns from `docs/cards_database.json` in
[miles2542/harmonies-bot](https://github.com/miles2542/harmonies-bot), commit
`a5ffa20f4d6206632eec2c83e93c39cff79283c8`, licensed under Apache-2.0.
The license is retained in `licenses/harmonies-bot-APACHE-2.0.txt`.
Changes: renamed IDs and colors, converted directional chains into axial hex
coordinates, reversed stacks to bottom-to-top, omitted prose descriptions.
No source-engine code or publisher artwork is included. Harmonies is designed
by Johan Benvenuto and published by Libellud; this implementation is unaffiliated.

## Wingspan mechanical card catalog

`src/agentbga/wingspan/birds.json` contains a transformed subset of
`src/assets/data/master.json` from [Wingsearch](https://github.com/navarog/wingsearch),
commit `43e5036de9e68fa9c4fabaf4c760412a887adf05` (2026-09-15 retrieval).
Wingsearch credits TawnyFrogmouth for its underlying card dataset and distributes
its project under GPL-3.0. The catalog's license is retained alongside the data in
`src/agentbga/wingspan/CATALOG_LICENSE.txt`; the transformed catalog is distributed
under that license. This source file contains the complete editable mechanical
catalog used by AgentBGA, with no compiled or hidden data dependencies.

Changes: selected 170 core birds without Swift-Start; renamed IDs and fields;
converted numeric values, food alternatives, nest types, and bonus flags;
replaced card prose with independently authored structured effect parameters;
excluded expansion-only name criteria (e.g. “tuft” for Anatomist). No artwork,
flavor text, card images, rulebook text, or Wingsearch application code is bundled.
The independent AgentBGA engine and renderer remain under the repository's license.

Wingspan is designed by Elizabeth Hargrave and published by Stonemaier Games.
This research implementation is unaffiliated and has not been certified by the publisher.
