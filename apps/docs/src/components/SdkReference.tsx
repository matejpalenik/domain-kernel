import reference from "@/generated/reference.json"
import site from "@/generated/site.json"

export function SdkReference() {
  return (
    <div>
      <p>
        {reference.symbols.length} public exports in the source for version{" "}
        {site.version}.
      </p>
      <ul className="grid list-none grid-cols-1 gap-1 pl-0 sm:grid-cols-2">
        {reference.symbols.map((symbol) => (
          <li key={symbol.name}>
            <a href={`#${symbol.name}`}>{symbol.name}</a>
          </li>
        ))}
      </ul>
      {reference.symbols.map((symbol) => (
        <section
          key={symbol.name}
          id={symbol.name}
          className="scroll-mt-24 border-t border-zinc-200 py-5 dark:border-zinc-800"
        >
          <h3 className="mt-0">{symbol.name}</h3>
          <p className="text-xs tracking-wider text-zinc-500 uppercase">
            {symbol.kind}
          </p>
          <p>{symbol.description}</p>
          <pre className="overflow-x-auto">
            <code>{symbol.signature}</code>
          </pre>
          {symbol.fields.length > 0 && (
            <>
              <h4>Typed fields</h4>
              <div
                className="overflow-x-auto"
                role="region"
                aria-label={`${symbol.name} typed fields`}
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Type</th>
                      <th>Declared default</th>
                    </tr>
                  </thead>
                  <tbody>
                    {symbol.fields.map((field) => (
                      <tr key={field.name}>
                        <td>
                          <code>{field.name}</code>
                        </td>
                        <td>
                          <code>{field.annotation}</code>
                        </td>
                        <td>
                          <code>{field.default || "—"}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {symbol.members.length > 0 && (
            <ul>
              {symbol.members.map((member) => (
                <li key={member.name}>
                  <code>{member.name}</code>: <code>{member.annotation}</code>
                </li>
              ))}
            </ul>
          )}
          <a
            className="text-sm"
            href={`https://github.com/matejpalenik/domain-kernel/blob/${site.revision}/${symbol.source}#L${symbol.line}`}
          >
            Read the implementation
          </a>
        </section>
      ))}
    </div>
  )
}
