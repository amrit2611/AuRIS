/**
 * Turn a raw API/network error string into something a human can read
 * without needing to know FastAPI status codes or LLM provider names.
 *
 * The frontend receives errors in one of two shapes:
 *
 *   1. Errors thrown by our `unwrap()` in api.ts:
 *        `"<status> <detail>"`  e.g. `"422 Column detection failed and ..."`
 *      The status is a 3-digit HTTP code; the detail is whatever
 *      FastAPI put in `body.detail`.
 *
 *   2. Errors thrown by the browser before a response arrives
 *      (backend down, DNS, CORS preflight rejected):
 *        `"Failed to fetch"` (Chromium), `"Load failed"` (Safari),
 *        `"NetworkError when attempting to fetch resource."` (Firefox).
 *
 * This module classifies both into a `{headline, hint, technical}`
 * triple so the UI can lead with a short, plain-English headline,
 * follow with one line of actionable hint, and hide the raw string
 * behind a "Show technical details" disclosure.
 */

export interface ClassifiedError {
  /** Short, plain-English headline. Never longer than ~40 chars. */
  headline: string;
  /** One sentence explaining likely cause and what to try next. */
  hint: string;
  /** The original error string, trimmed for display. */
  technical: string;
}

const MAX_TECHNICAL_CHARS = 500;

function trimTechnical(raw: string): string {
  const cleaned = raw.trim();
  if (cleaned.length <= MAX_TECHNICAL_CHARS) return cleaned;
  return cleaned.slice(0, MAX_TECHNICAL_CHARS) + "…";
}

function parseStatus(raw: string): { status: number | null; body: string } {
  // Matches leading "NNN " where NNN is 3 digits.
  const match = raw.match(/^(\d{3})\s+([\s\S]*)$/);
  if (!match) return { status: null, body: raw };
  return { status: Number(match[1]), body: match[2] };
}

function isNetworkError(raw: string): boolean {
  const lc = raw.toLowerCase();
  return (
    lc.includes("failed to fetch") ||
    lc.includes("load failed") ||
    lc.includes("networkerror") ||
    lc.includes("network request failed")
  );
}

export function classifyError(raw: string): ClassifiedError {
  const technical = trimTechnical(raw);

  if (isNetworkError(raw)) {
    return {
      headline: "Backend not reachable",
      hint:
        "The FastAPI backend isn't responding. Check that uvicorn is running on the port NEXT_PUBLIC_API_URL points at.",
      technical,
    };
  }

  const { status, body } = parseStatus(raw);
  const lc = body.toLowerCase();

  // 422: mapping failed to cover all four required fields.
  if (
    status === 422 &&
    lc.includes("after column detection") &&
    lc.includes("missing required columns")
  ) {
    return {
      headline: "Some required columns are missing",
      hint:
        "AuRIS needs vendor, amount, date, and invoice_id. The auto-mapper couldn't fill all four from your headers. Rename the closest columns and re-upload.",
      technical,
    };
  }

  // 422: LLM column detection itself failed (bad key, provider error, wide CSV
  // that couldn't be mapped).
  // Note: the backend's error template ALWAYS contains the substring
  // "GROQ_API_KEY" (as part of the "or ensure GROQ_API_KEY is set" hint).
  // Match on the specific "environment variable is required" phrase from
  // schema.py's actual missing-key error, not on the template.
  if (status === 422 && lc.includes("column detection failed")) {
    if (lc.includes("environment variable is required")) {
      return {
        headline: "AI features not configured on the backend",
        hint:
          "This CSV doesn't already use the vendor/amount/date/invoice_id schema, so AuRIS needs an LLM to map its columns. Set GROQ_API_KEY on the backend, or rename the columns manually and re-upload.",
        technical,
      };
    }
    return {
      headline: "Couldn't auto-detect the columns",
      hint:
        "The LLM tried to map your CSV headers but the mapping came back empty or invalid. This is usually a transient LLM issue; try uploading again in a moment.",
      technical,
    };
  }

  // 400 file-shape errors.
  if (status === 400 && lc.includes("only csv files are supported")) {
    return {
      headline: "That file isn't a CSV",
      hint: "AuRIS only accepts .csv files. Export your data as CSV and try again.",
      technical,
    };
  }
  if (status === 400 && lc.includes("csv is empty")) {
    return {
      headline: "The CSV is empty",
      hint: "The uploaded file has no rows. Check that it saved correctly and re-upload.",
      technical,
    };
  }
  if (status === 400 && lc.includes("could not parse csv")) {
    return {
      headline: "Couldn't read the CSV",
      hint:
        "The file looks malformed (unclosed quotes, mixed delimiters, or a truncated download are common causes). Open it in Excel or a text editor to check, then re-upload.",
      technical,
    };
  }

  // 400 from /summarize with no rows.
  if (status === 400 && lc.includes("report_rows is required")) {
    return {
      headline: "Nothing to summarise yet",
      hint: "Upload and analyse a CSV first, then generate the AI summary.",
      technical,
    };
  }

  // 503 from /summarize: LLM provider issue.
  if (status === 503) {
    return {
      headline: "AI summary temporarily unavailable",
      hint:
        "The LLM provider returned an error. Try again in a few seconds; if it keeps failing, GROQ_API_KEY may be missing or the model may be rate-limited.",
      technical,
    };
  }

  // 5xx catch-all.
  if (status !== null && status >= 500) {
    return {
      headline: "The backend hit an error",
      hint: "The FastAPI backend returned a server-side error. Check the uvicorn logs for the stack trace.",
      technical,
    };
  }

  // Anything else.
  return {
    headline: "Something went wrong",
    hint: "Try again. If it keeps happening, see the technical details below.",
    technical,
  };
}
