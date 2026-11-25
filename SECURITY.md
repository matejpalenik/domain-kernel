# Security policy

Security is a core consideration in the design, development and distribution of Domain Kernel.

As an embeddable SDK that processes documents, interacts with language models and produces reusable business domain models, Domain Kernel considers security across three areas:

- **Supply-chain integrity.** Protecting the integrity of the SDK, its dependencies and distributed release artifacts.
- **Runtime security.** Addressing risks associated with document processing, model inference and application integration.
- **Knowledge integrity.** Preserving the provenance, review history and integrity of published domain models.

This policy describes the project's security practices, vulnerability reporting process and the responsibilities of maintainers and consuming applications.

## Supported versions

Domain Kernel is currently an alpha, non-commercial open-source project.

| Version | Security support |
|---|---|
| Latest development revision | Best effort |
| Latest alpha release | Best effort |
| Historical releases | Not guaranteed |
| Stable releases | Not yet available |

The project does not currently provide a guaranteed security-support period or contractual security commitments.

Consumers should use the latest available revision or release when evaluating the SDK and independently assess its suitability for their environments.

A future stable or commercial release will require an explicit supported-version policy and security-support period.

## Reporting a vulnerability

We welcome good-faith security research and responsible vulnerability disclosure.

Report suspected vulnerabilities privately using **Report a vulnerability** on the [GitHub Security Advisories page](https://github.com/matejpalenik/domain-kernel/security/advisories).

If private vulnerability reporting is unavailable, contact the maintainer, [Matej Palenik](mailto:matejpale@gmail.com).

Please do not disclose an unpatched vulnerability through a public GitHub issue, pull request or discussion.

### What to include

To help reproduce and assess a vulnerability, provide:

- The affected SDK version or commit.
- The optional dependencies, adapters and configuration involved.
- A description of the vulnerability and its potential impact.
- A minimal reproduction or proof of concept.
- Any known mitigations or workarounds.

Remove credentials, personal data, confidential documents and other sensitive information from your report.

### Vulnerability handling

The maintainer will assess reported vulnerabilities, determine their impact and coordinate reproduction, remediation and disclosure with the reporter.

Where appropriate, fixes and mitigation guidance will be communicated through GitHub Security Advisories and release notes.

Reports are handled on a best-effort basis. The project does not currently guarantee response or remediation deadlines.

### Responsible disclosure

Security researchers are encouraged to:

- Conduct testing in environments they own or are authorized to access.
- Avoid accessing, modifying or disclosing third-party data.
- Avoid disrupting services or causing unnecessary damage.
- Coordinate public disclosure with the maintainer to allow reasonable time for investigation and remediation.

## Supply-chain security

Domain Kernel applies preventative and detective controls throughout its development and release processes.

### Dependency management

Python dependencies are managed using `uv` and a committed dependency lockfile.

The project applies a seven-day minimum release age to registry artifacts, including transitive dependencies and optional, development and build requirements. Artifacts without the required publication timestamps are excluded.

The documentation workspace applies an equivalent minimum release age through `pnpm`, together with provenance verification, restrictions on dependency sources and explicit approval of dependency build scripts.

These controls provide time for newly compromised packages to be identified before adoption. They reduce exposure to supply-chain attacks but do not establish that an older dependency is safe.

Dependency management follows these principles:

- Dependency changes are reviewed before merging.
- CI and release workflows use locked or frozen dependency installations.
- Lockfiles are regenerated only as part of intentional dependency changes.
- Dependency sources and provenance are evaluated where supported.
- Dependency build scripts require explicit approval where supported.
- Automated dependency updates follow the project's configured cooldown policies.

Dependencies and assets outside these controls, including Git dependencies, direct-URL dependencies, downloaded model assets, Python interpreters and independently installed tools, require separate assessment.

### Vulnerability monitoring

The committed Python dependency lockfile is audited on pull requests, pushes to `main`, release tags and a weekly schedule.

The documentation workspace also provides dependency auditing covering development dependencies.

These checks assess the project's configured dependency graph. They do not continuously monitor historical releases or the dependency versions resolved by consuming applications.

### Security update exceptions

Security fixes may require an exception to the dependency cooldown policy.

Before approving an exception, the maintainer must assess the risk of delaying remediation and verify the relevant upstream release.

Exceptions must be:

- Limited to the affected dependency and approved release.
- Supported by a documented security justification.
- Time-limited and explicitly approved.
- Verified using the applicable dependency and project checks.
- Removed once the ordinary dependency policy can be restored.

Automated security-update pull requests do not independently authorize exceptions to local dependency policies or required security checks.

Historical exceptions and their remediation records are maintained separately from this policy.

## Repository and CI/CD security

The project applies repository protections and workflow restrictions to reduce the risk of unauthorized or unreviewed changes.

These controls include:

- Pull requests and required CI checks for changes to the main branch.
- Review requirements for security-sensitive files.
- Full commit SHA pinning of GitHub Actions.
- Restrictions on permitted GitHub Actions repositories.
- Verification of action identities, references and provenance through the committed `actions.lock`.
- Protected release tags.
- Restricted workflow permissions, including deployment-specific write permissions.

The project currently has a sole maintainer who may bypass designated review requirements but remains subject to required CI checks.

The `actions.lock` verification is implemented through project CI. It does not imply that GitHub's native lockfile execution policy is enabled.

Repository security settings and their maintenance procedures are documented in [Repository security settings](.github/security-settings.md).

## Release integrity

Release workflows produce supply-chain evidence that enables consumers to inspect and verify distributed artifacts.

This includes:

- CycloneDX Software Bills of Materials (SBOMs).
- Artifact checksums.
- Signed artifact provenance.

Generated SBOMs are distributed as release assets rather than committed source files.

The Python release SBOMs do not include the separate JavaScript documentation workspace.

Consumers should verify downloaded release artifacts and assess their dependency inventories before introducing the SDK into sensitive or production environments.

See the [release guide](docs/releasing.md#verify-downloaded-release-assets) for verification procedures, artifact coverage and limitations.

## Runtime security

Domain Kernel runs within a consuming application's environment rather than as an independently managed service.

Its security therefore depends on both the SDK implementation and the configuration, infrastructure and controls provided by the consuming application.

### Untrusted inputs

Source documents, extracted content, language model responses and imported domain model bundles should be treated as untrusted inputs.

Relevant security risks include:

- Malformed or malicious documents targeting document parsers.
- Excessive resource consumption during document processing or inference.
- Instructions embedded in documents attempting to influence language model behaviour.
- Invalid, misleading or malicious generated model proposals.
- Manipulated or malformed published domain model bundles.

Consuming applications should apply appropriate input validation, resource limits, access controls and runtime isolation according to their threat model.

### Language model security

Language model responses are probabilistic and may contain incorrect, incomplete or manipulated information.

Domain Kernel separates automated discovery from the acceptance and publication of domain knowledge. Generated proposals are not authoritative merely because they have been produced by a language model.

Evidence-backed discovery and human review support the assessment of generated proposals. They do not guarantee factual correctness or eliminate the risk of prompt injection, malicious source documents or model manipulation.

Consuming applications remain responsible for selecting and configuring appropriate model providers, protecting credentials and controlling the information transmitted to those providers.

### Data security and privacy

Source documents may contain confidential business information, personal data or other sensitive material.

Consuming applications are responsible for establishing appropriate controls for:

- Document access and authorization.
- Encryption in transit and at rest.
- Credential and secret management.
- Data retention and deletion.
- Data residency and processing requirements.
- Information disclosed to external model providers.
- Logging and monitoring of sensitive operations.

Evidence references, review records and published model bundles may also contain or expose sensitive business information and should be protected accordingly.

## Knowledge integrity

Domain Kernel is designed to support traceable and reviewable business domain modeling.

The SDK distinguishes source evidence, generated proposals, review decisions and published model versions.

This separation supports the following principles:

- Modeling proposals should be inspectable against their supporting evidence.
- Generated proposals should not be treated as verified business knowledge without review.
- Review decisions should preserve their rationale and responsible actors.
- Published models should identify the specific version being distributed.
- Consumers should be able to inspect the provenance of published knowledge.

These mechanisms support knowledge integrity, but they do not establish the authenticity of source documents, the identity or authority of reviewers, or the factual correctness of every accepted definition.

Consuming applications must establish appropriate authentication, authorization and access controls for source ingestion, review, publication and model distribution.

Consumers should independently establish the authenticity and integrity of domain model bundles received from external or untrusted sources.

## Shared security responsibilities

Security is a shared responsibility between Domain Kernel and the applications that integrate it.

| Responsibility | Domain Kernel | Consuming application |
|---|:---:|:---:|
| Security of the SDK implementation | ✓ | |
| Integrity of official SDK release artifacts | ✓ | |
| Monitoring of the project's committed dependencies | ✓ | |
| Validation at SDK and application boundaries | ✓ | ✓ |
| Secure configuration of SDK adapters | | ✓ |
| Monitoring of deployed dependencies | | ✓ |
| Authentication and authorization | | ✓ |
| Document and storage access controls | | ✓ |
| Credential and secret management | | ✓ |
| Model provider selection and configuration | | ✓ |
| Runtime isolation and resource limits | | ✓ |
| Data protection and retention | | ✓ |
| Authenticity of externally supplied documents | | ✓ |
| Authorization of review and publication operations | | ✓ |
| Secure distribution of domain model bundles | | ✓ |
| Deployment-specific regulatory compliance | | ✓ |

This allocation describes security ownership. It does not imply that every listed control has been implemented or independently verified.

Consumers must assess the SDK and their integration against the security requirements of their intended deployment.

## Regulatory considerations

Domain Kernel is currently developed as a non-commercial open-source project.

Its security practices are informed by established software supply-chain security principles and relevant regulatory developments, including the European Union's Cyber Resilience Act (CRA).

The project does not currently claim CRA conformity, security certification or independent security accreditation.

The applicability of regulatory obligations must be reassessed if the project's distribution model, monetisation or organisational role changes.

Consumers integrating Domain Kernel into commercial products or regulated environments remain responsible for assessing the obligations applicable to those products and environments.

Relevant references:

- [European Commission: CRA and open source](https://digital-strategy.ec.europa.eu/en/policies/cra-open-source)
- [European Commission: Cyber Resilience Act](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act)
- [Regulation (EU) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj)

## Security limitations

Domain Kernel is under active development. Its security controls and architectural boundaries continue to evolve.

The existence of dependency audits, repository protections, SBOMs, artifact provenance and evidence-backed modeling does not establish that the SDK is free of vulnerabilities or suitable for every security-sensitive application.

Consumers should conduct an appropriate security assessment before processing sensitive information or introducing the SDK into production environments.

## Further documentation

| Resource | Description |
|---|---|
| [Security architecture](ARCHITECTURE.md#11-security-architecture) | Trust boundaries and the host's residual responsibilities. |
| [Repository security settings](.github/security-settings.md) | Repository protections and workflow security configuration. |
| [Release guide](docs/releasing.md) | Release integrity, SBOM generation and artifact verification. |
| [Contributing](CONTRIBUTING.md) | Development practices and required project checks. |
| [Security advisories](https://github.com/matejpalenik/domain-kernel/security/advisories) | Published advisories and private vulnerability reporting. |
