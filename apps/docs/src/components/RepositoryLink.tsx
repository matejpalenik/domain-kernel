import site from "@/generated/site.json"

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
