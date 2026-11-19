/**
 * screens/NotFoundScreen.tsx: what a URL with no screen shows.
 *
 * BUSINESS: a mistyped or old link still lands inside LoanIQ, with the header's
 *   synthetic-data warning and the sidebar, and a way back to the Loan Tape.
 * TECH: the "*" route in App.tsx matches any path no other route matched. FastAPI
 *   already sends index.html for any non-API URL; this is the browser-side half.
 */
import { Link } from "react-router";

/**
 * The not-found screen.
 * BUSINESS: never a dead end. TECH: a plain React Router Link back to "/".
 */
export function NotFoundScreen() {
  return (
    <div className="screen">
      <h2>Screen not found</h2>
      <p>
        There is no screen at this address. <Link to="/">Go to the Loan Tape</Link>.
      </p>
    </div>
  );
}
