export function ModelJourney() {
  const steps = [
    ["01", "Evidence", "Documents, tables and existing terminology"],
    ["02", "Meaning", "Proposed definitions with source support"],
    ["03", "Review", "Explicit choices, corrections and provenance"],
    ["04", "Contract", "A versioned model for your application"],
  ]
  return (
    <figure className="not-prose my-10">
      <ol
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="The modelling journey"
      >
        {steps.map(([number, title, description]) => (
          <li
            key={number}
            className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-800/40"
          >
            <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400">
              {number}
            </span>
            <strong className="mt-3 block text-lg text-zinc-900 dark:text-white">
              {title}
            </strong>
            <span className="mt-2 block text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {description}
            </span>
          </li>
        ))}
      </ol>
    </figure>
  )
}
