/**
 * screens/AboutScreen.tsx: the About page (Showcase group, /about).
 *
 * Where it sits: sidebar "About" -> route /about (App.tsx) -> [AboutScreen] ->
 * content/about.md (words) and brand/logo/loaniq-labs_stacked_dark-bg.svg (logo).
 *
 * BUSINESS: a first-time visitor learns what LoanIQ does for a mortgage capital
 *   markets desk, the approach (synthetic data, public sources, tests gate every
 *   change) and the architecture, under the LoanIQ Labs logo.
 * TECH:
 *   - The stacked logo is the kit's choice for square spaces such as an About page
 *     (brand/README.txt), and the dark-background version matches the page.
 *     It is imported through the "@brand" alias, so brand/ stays the only copy and
 *     Vite publishes just this file, with a hashed name.
 *   - The logo is decorative here (alt=""): the header's logo already names
 *     LoanIQ Labs, and about.md's first heading names the page.
 *   - No Explain panel: this page is itself the explanation (decided in Step 1f).
 */
import logoUrl from "@brand/logo/loaniq-labs_stacked_dark-bg.svg";
import { ShowcaseMarkdown } from "../components/ShowcaseMarkdown";
import { showcasePages } from "../content/content";

/**
 * The About page.
 * BUSINESS: what LoanIQ is, in the owner's words from content/about.md.
 * TECH: static content bundled at build time; no API calls, so it renders instantly.
 */
export function AboutScreen() {
  return (
    <div className="screen showcase">
      <img className="showcase-logo" src={logoUrl} alt="" />
      <ShowcaseMarkdown markdown={showcasePages.about} />
    </div>
  );
}
