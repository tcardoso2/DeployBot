const fs = require("fs");
const path = require("path");

const distDir = path.join(__dirname, "dist");
fs.rmSync(distDir, { recursive: true, force: true });
fs.mkdirSync(distDir, { recursive: true });
fs.writeFileSync(
  path.join(distDir, "index.html"),
  "<html><body><h1>Nested NPM App</h1><p>Packaged by fixture build.</p></body></html>\n",
  "utf8",
);
