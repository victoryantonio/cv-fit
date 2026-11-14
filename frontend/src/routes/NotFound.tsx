import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="space-y-3">
      <h1 className="text-title">Page not found</h1>
      <p className="text-dense text-muted">
        This address does not match a screen. The job or packet may have been
        deleted.
      </p>
      <Link to="/" className="inline-block text-dense text-accent underline">
        Back to Home
      </Link>
    </div>
  );
}
