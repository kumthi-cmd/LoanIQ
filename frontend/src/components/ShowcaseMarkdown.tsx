/**
 * components/ShowcaseMarkdown.tsx: renders one whole Markdown file from content/ as
 * a Showcase page section.
 *
 * Where it sits: content/*.md -> content.ts (showcasePages, agentExplainer) ->
 * [ShowcaseMarkdown] -> AboutScreen, HowItWasBuiltScreen, AgentExplainer (Step 4d).
 *
 * BUSINESS: the About page, How it was built and the build log are written as plain
 *   Markdown files that you edit without touching code; this shows them as the page.
 * TECH:
 *   - react-markdown turns Markdown into React elements. It does not inject raw HTML,
 *     so a stray <script> in a content file is shown as text, never run.
 *   - Heading levels shift down by one (# -> h2, ## -> h3, ...). The page's one <h1>
 *     is the LoanIQ Labs logo in the header, and screen titles are h2, so a
 *     screen reader's heading outline stays in order.
 *   - titleId (optional) puts an id on the file's top heading (# -> h2), so a dialog
 *     can name itself after it with aria-labelledby (AgentExplainer).
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
 *   titleId, when given, becomes the id of every "#" heading (a content file has one).
 */
export function ShowcaseMarkdown({ markdown, titleId }: { markdown: string; titleId?: string }) {
  // TECH: only build a new components map when an id is wanted; otherwise reuse the
  //   shared one, so the About and How it was built pages are unchanged.
  const components: Components = titleId
    ? { ...shiftedHeadings, h1: ({ node: _node, ...props }) => <h2 {...props} id={titleId} /> }
    : shiftedHeadings;
  return (
    <div className="showcase-text">
      <Markdown components={components}>{markdown}</Markdown>
    </div>
  );
}
