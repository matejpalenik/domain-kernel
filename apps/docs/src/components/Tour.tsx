import site from "@/generated/site.json"

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/domain-kernel"

export function TourChapters() {
  return (
    <ol>
      {site.chapters.map((chapter) => (
        <li key={chapter.anchor}>
          <a href={`${basePath}/tour/reading/#${chapter.anchor}`}>
            {chapter.title}
          </a>
        </li>
      ))}
    </ol>
  )
}

export function TourLinks() {
  return (
    <div className="not-prose my-8 grid gap-4 sm:grid-cols-2">
      <a
        href={`${basePath}/tour/reading/`}
        className="rounded-xl border border-emerald-500/30 bg-emerald-50 p-6 text-emerald-950 dark:bg-emerald-950/30 dark:text-emerald-100"
      >
        <strong className="block text-lg">Read the complete tour →</strong>
        <span className="mt-2 block text-sm">
          See the evidence, correction, and two published versions. No
          installation needed.
        </span>
      </a>
      <a
        href={`https://github.com/matejpalenik/domain-kernel/archive/${site.revision}.zip`}
        className="rounded-xl border border-zinc-300 p-6 text-zinc-900 dark:border-zinc-700 dark:text-zinc-100"
      >
        <strong className="block text-lg">
          Download the matching source →
        </strong>
        <span className="mt-2 block text-sm">
          The notebook, fixtures, helpers and SDK together. Open the repository
          folder in VS Code.
        </span>
      </a>
    </div>
  )
}

export function RepositoryLink({
  path,
  children,
}: {
  path: string
  children: React.ReactNode
}) {
  return (
    <a
      href={`https://github.com/matejpalenik/domain-kernel/blob/${site.revision}/${path}`}
    >
      {children}
    </a>
  )
}
