import "./logging.js";
import log4js from "log4js";
import express from "express";
import metadata from "./metadata.js";
import transport from "./transport.js";
import cors from "cors";

await metadata.init();

const l = log4js.getLogger();
const PORT = 3000;

const app = express();
app.use(express.json());
app.use(
  cors({
    origin: "*",
    methods: ["GET", "POST", "DELETE", "UPDATE", "PUT", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization"],
  })
);

// app.use(httpContextMiddleware);
// app.use();

app.get("/health", (req, res) => {
  res.json(metadata.all);
});

app.use(async (req, res, next) => {
  l.debug(`> ${req.method} ${req.originalUrl}`);
  l.debug(req.body);
  // l.debug(req.headers);
  return next();
});

await transport.bootstrap(app);

await app.listen(PORT, () => {
  l.debug(metadata.all);
  l.debug(`listening on http://localhost:${PORT}`);
});
