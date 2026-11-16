import { createServer } from "node:http"
import { readFile, stat } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".txt": "text/plain",
  ".woff2": "font/woff2",
}

export function startPreview({
  directory = fileURLToPath(new URL("../out", import.meta.url)),
  basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/domain-kernel",
  port = 3001,
} = {}) {
  const root = path.resolve(directory)
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost")
      const pathname = decodeURIComponent(url.pathname)
      if (!pathname.startsWith(basePath + "/"))
        throw new Error("Outside site prefix")
      let file = path.resolve(root, "." + pathname.slice(basePath.length))
      if (!file.startsWith(root + path.sep) && file !== root)
        throw new Error("Outside site directory")
      if ((await stat(file)).isDirectory()) file = path.join(file, "index.html")
      const body = await readFile(file)
      response.writeHead(200, {
        "Content-Type": types[path.extname(file)] ?? "application/octet-stream",
        "X-Content-Type-Options": "nosniff",
      })
      response.end(body)
    } catch {
      response.writeHead(404, { "Content-Type": "text/html; charset=utf-8" })
      response.end(
        await readFile(path.join(root, "404.html")).catch(
          () => "Page not found"
        )
      )
    }
  })
  return new Promise((resolve, reject) => {
    server.once("error", reject)
    server.listen(port, "127.0.0.1", () => resolve(server))
  })
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const port = Number(process.env.PORT ?? 3001)
  await startPreview({ port })
  console.log(
    `Static documentation: http://localhost:${port}${process.env.NEXT_PUBLIC_BASE_PATH ?? "/domain-kernel"}/`
  )
}
