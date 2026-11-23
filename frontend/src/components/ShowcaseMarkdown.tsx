/**
 * components/ShowcaseMarkdown.tsx: renders one whole Markdown file from content/ as
 * a Showcase page section.
 *
 * Where it sits: content/*.md -> content.ts (showcasePages) -> [ShowcaseMarkdown] ->
 * AboutScreen, HowItWasBuiltScreen.
 *
 * BUSINESS: the About page, How it was built and the build log are written as plain
 *   Markdown files that you edit without touching code; this shows them as the page.
 * TECH:
 *   - react-markdown turns Markdown into React elements. It does not inject raw HTML,
 *     so a stray <script> in a content file is shown as text, never run.
 *   - Heading levels shift down by one (# -> h2, ## -> h3, ...). The page's one <h1>
 *     is the LoanIQ Labs logo in the header, and screen titles are h2, so a
 *     screen reader's heading outline stays in order.
 *   - Markdown links become plain <a href> elements. The Showcase files have none
 *     today; a link to a LoanIQ path would reload the page rather than use the router.
 */
import Markdown, { type Components } from "react-markdown";

// TECH: react-markdown's "components" option swaps the element used for each tag.
//   Each mapping drops react-markdown's extra "node" prop and passes the rest on.
const shiftedHeadings: Components = {
  h1: ({ node: _node, ...props }) => <h2 {...props} />,
  h2: ({ node: _node, ...props }) => <h3 {...props} />,
  h3: ({ node: _node, ...props }) => <h4 {...props} />,
  h4: ({ node: _node, ...props }) => <h5 {...props} />,
};

/**
 * One Markdown file, rendered.
 * BUSINESS: the words exactly as written in content/.
 * TECH: markdown is the raw file text; an empty string renders an empty section.
 */
export function ShowcaseMarkdown({ markdown }: { markdown: string }) {
  return (
    <div className="showcase-text">
      <Markdown components={shiftedHeadings}>{markdown}</Markdown>
    </div>
  );
}
