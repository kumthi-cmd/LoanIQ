/**
 * components/BuildFacts.tsx: the "By the numbers" tiles on How it was built.
 *
 * Where it sits: test.ps1 (after every layer passes) -> content/build-facts.json ->
 * content.ts (parseBuildFacts) -> [BuildFacts] -> HowItWasBuiltScreen.
 *
 * BUSINESS: a visitor sees the evidence behind "tests gate every change": how many
 *   back-end, front-end and browser tests ran, back-end coverage, and how many commits
 *   it took, as of the last full test run on the developer's PC. The hosted site shows
 *   the numbers from the last committed run (CI does not rewrite the file).
 * TECH: a description list (<dl>), so a screen reader pairs each label with its
 *   number. Any missing fact shows as an em dash instead of breaking the page.
 *   The short tile labels live here, like other UI labels ("Planned"); the
 *   explanation of where the numbers come from is in content/how-it-was-built.md.
 *   Counts use US thousands separators; coverage keeps one decimal, in percent.
 */
import type { BuildFacts as BuildFactsData } from "../content/content";

/** TECH: shown for a fact the file does not have. */
export const MISSING = "—";

/** Format a count with thousands separators, or a dash when it is missing. */
function count(n: number | undefined): string {
  return n === undefined ? MISSING : n.toLocaleString("en-US");
}

/**
 * The "By the numbers" tiles.
 * BUSINESS: six facts, each a number a reviewer can check against the repo.
 * TECH: facts is already validated by parseBuildFacts; undefined fields show MISSING.
 */
export function BuildFacts({ facts }: { facts: BuildFactsData }) {
  const items: [label: string, value: string][] = [
    ["Back-end tests", count(facts.backendTests)],
    ["Front-end tests", count(facts.frontendTests)],
    ["End-to-end tests", count(facts.e2eTests)],
    // BUSINESS: share of back-end lines run by the tests, in percent; the floor is 80%.
    ["Back-end coverage", facts.backendCoverage === undefined ? MISSING : `${facts.backendCoverage.toFixed(1)}%`],
    ["Commits", count(facts.commits)],
    ["Last full test run", facts.date ?? MISSING],
  ];
  // TECH: no heading or prose here: the "## By the numbers" heading and its sentence
  //   are the last section of content/how-it-was-built.md, rendered just above.
  return (
    <dl className="build-facts" aria-label="By the numbers">
      {items.map(([label, value]) => (
        <div key={label} className="build-fact">
          <dt>{label}</dt>
          <dd className="mono">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
