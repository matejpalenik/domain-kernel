import glob from "fast-glob"
import { type Metadata } from "next"

import { pageMetadata as introductionMetadata } from "./page.mdx"

import { Providers } from "@/app/providers"
import { Layout } from "@/components/Layout"
import { type Section } from "@/components/SectionProvider"

import "@/styles/tailwind.css"

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.DOCS_SITE_URL ?? "https://matejpalenik.github.io/domain-kernel/"
  ),
  ...introductionMetadata,
  title: {
    template: "%s - Domain Kernel documentation",
    default: introductionMetadata.title,
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pages = await glob("**/*.mdx", { cwd: "src/app" })
  const allSectionsEntries = (await Promise.all(
    pages.map(async (filename) => [
      ("/" + filename.replace(/(^|\/)page\.mdx$/, "")).replace(/\/$/, "") ||
        "/",
      (await import(`./${filename}`)).sections,
    ])
  )) as Array<[string, Array<Section>]>
  const allSections = Object.fromEntries(allSectionsEntries)

  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="flex min-h-full bg-white antialiased dark:bg-zinc-900">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:rounded focus:bg-white focus:p-3 focus:text-zinc-900"
        >
          Skip to content
        </a>
        <Providers>
          <div className="w-full">
            <Layout allSections={allSections}>{children}</Layout>
          </div>
        </Providers>
      </body>
    </html>
  )
}
