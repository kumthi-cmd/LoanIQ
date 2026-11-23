/**
 * screens/HowItWasBuiltScreen.tsx: the How it was built page (Showcase, /how-it-was-built).
 *
 * Where it sits: sidebar "How it was built" -> route /how-it-was-built (App.tsx) ->
 * [HowItWasBuiltScreen] -> content/how-it-was-built.md, content/build-facts.json
 * (written by test.ps1) and content/build-log.md.
 *
 * BUSINESS: shows how LoanIQ was built AI-first with Claude Code: the approach and
 *   standards, the numbers that back them (tests, coverage, commits), then the build
 *   log, one entry per step with the owner's decisions and review changes.
 * TECH:
 *   - Order on the page: how-it-was-built.md (which ends with "By the numbers"),
 *     the facts tiles right under that heading, then the build log.
 *   - All three are bundled at build time, so the hosted site shows the facts from
 *     the last committed test run; missing facts show as a dash (BuildFacts).
 *   - No Explain panel: this page is itself the explanation (decided in Step 1f).
 */
import { BuildFacts } from "../components/BuildFacts";
import { ShowcaseMarkdown } from "../components/ShowcaseMarkdown";
import { buildFacts, showcasePages } from "../content/content";

/**
 * The How it was built page.
 * BUSINESS: the AI-first story, the evidence, then the step-by-step log.
 * TECH: static content; no API calls.
 */
export function HowItWasBuiltScreen() {
  return (
    <div className="screen showcase">
      <ShowcaseMarkdown markdown={showcasePages.howItWasBuilt} />
      <BuildFacts facts={buildFacts} />
      <ShowcaseMarkdown markdown={showcasePages.buildLog} />
    </div>
  );
}
