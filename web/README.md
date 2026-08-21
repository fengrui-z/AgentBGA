# AgentBGA live table

Static React frontend for the local multi-game AgentBGA server. It renders dedicated
tables for Splendor, Azul, Ark Nova, Brass: Birmingham, and Century: Spice Road.

```console
npm install
npm run build
cd ..
./agentbga web
```

Open `http://127.0.0.1:8765`. During development, keep `./agentbga web`
running and use `npm run dev`; `/api` is proxied to port 8765.

The production build uses `output: "export"` so the Python standard-library
server can serve `dist/client` without a Node process. This UI deliberately has
no hosted API: it accepts model credentials and therefore stays localhost-only.
