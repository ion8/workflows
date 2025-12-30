#!/usr/bin/env npx tsx
/**
 * Link Checker Script
 * Crawls a website and checks for broken links and missing images.
 * Automatically discovers pages from sitemap.xml
 *
 * Usage: npx tsx scripts/link-checker.ts <base-url>
 * Example: npx tsx scripts/link-checker.ts https://efficient-legal-preview.vercel.app
 *
 * Note: The website must have a sitemap.xml at <base-url>/sitemap.xml
 */

// @ts-ignore
import * as fs from "fs";

declare const process: {
  argv: string[];
  exit: (code: number) => never;
};

/**
 * Represents a broken link found during crawling
 */
interface BrokenLink {
  /** The page path where the broken link was found */
  page: string;
  /** The original href attribute value */
  url: string;
  /** The resolved absolute URL */
  fullUrl: string;
  /** HTTP status code or error message (e.g., "Timeout", "Connection failed") */
  status: number | string;
  /** Whether the link points to the same domain as BASE_URL */
  isInternal: boolean;
}

/**
 * Represents a missing or inaccessible image found during crawling
 */
interface MissingImage {
  /** The page path where the missing image was found */
  page: string;
  /** The original src attribute value */
  src: string;
  /** The resolved absolute URL */
  fullUrl: string;
  /** HTTP status code or error message (e.g., "Timeout", "Connection failed") */
  status: number | string;
}

/**
 * Aggregated results from the link checking process
 */
interface Results {
  /** All broken links discovered across all pages */
  brokenLinks: BrokenLink[];
  /** All missing images discovered across all pages */
  missingImages: MissingImage[];
  /** Set of unique link URLs that have been checked (prevents duplicate checks) */
  checkedLinks: Set<string>;
  /** Set of unique image URLs that have been checked (prevents duplicate checks) */
  checkedImages: Set<string>;
  /** Total number of pages successfully crawled */
  pagesCrawled: number;
}

/**
 * Result of checking a single URL's accessibility
 */
interface CheckUrlResult {
  /** Whether the URL returned a 2xx status code */
  ok: boolean;
  /** HTTP status code or error message */
  status: number | string;
}

const BASE_URL: string | undefined = process.argv[2];

if (!BASE_URL) {
  console.error("Usage: npx tsx scripts/link-checker.ts <base-url>");
  process.exit(1);
}

const results: Results = {
  brokenLinks: [],
  missingImages: [],
  checkedLinks: new Set(),
  checkedImages: new Set(),
  pagesCrawled: 0,
};

/**
 * Checks if a URL is accessible by making a HEAD request
 *
 * @param url - The absolute URL to check
 * @returns Object containing ok status and HTTP status code or error message
 * @remarks
 * - Uses HEAD request with 10 second timeout
 * - Follows redirects automatically
 * - Returns "Timeout" or "Connection failed" for network errors
 */
async function checkUrl(url: string): Promise<CheckUrlResult> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);

    const response = await fetch(url, {
      method: "HEAD",
      signal: controller.signal,
      redirect: "follow",
    });

    clearTimeout(timeout);
    return { ok: response.ok, status: response.status };
  } catch (error) {
    return {
      ok: false,
      status:
        (error as Error).name === "AbortError"
          ? "Timeout"
          : "Connection failed",
    };
  }
}

/**
 * Determines if a URL belongs to the same domain as BASE_URL
 *
 * @param url - The URL to check (can be relative or absolute)
 * @returns true if the URL's hostname matches BASE_URL's hostname, false otherwise
 */
function isInternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url, BASE_URL);
    const base = new URL(BASE_URL!);
    return parsed.hostname === base.hostname;
  } catch {
    return false;
  }
}

/**
 * Resolves a relative or absolute URL against a base page URL
 *
 * @param href - The URL to resolve (can be relative or absolute)
 * @param pageUrl - The base page URL to resolve against
 * @returns The resolved absolute URL, or null if the URL is invalid
 */
function resolveUrl(href: string, pageUrl: string): string | null {
  try {
    return new URL(href, pageUrl).href;
  } catch {
    return null;
  }
}

/**
 * Discovers the sitemap URL for a given website following web standards
 *
 * @param baseUrl - The base URL of the website to check
 * @returns The sitemap URL if found, null otherwise
 * @remarks
 * Discovery process:
 * 1. Checks robots.txt for Sitemap directive (per https://www.robotstxt.org/robotstxt.html)
 * 2. Tries standard locations: /sitemap.xml and /sitemap_index.xml
 * 3. Returns null if no sitemap found (caller should handle fallback)
 */
async function discoverSitemap(baseUrl: string): Promise<string | null> {
  // Step 1: Check robots.txt for Sitemap directive
  // Many sites declare their sitemap location in robots.txt following the standard:
  // https://www.robotstxt.org/robotstxt.html
  try {
    const robotsUrl = `${baseUrl}/robots.txt`;

    const response = await fetch(robotsUrl);
    if (response.ok) {
      const robotsTxt = await response.text();

      // Look for "Sitemap: <url>" directive (case-insensitive)
      const sitemapMatch = robotsTxt.match(/Sitemap:\s*(.+)/i);
      if (sitemapMatch) {
        const sitemapUrl = sitemapMatch[1].trim();

        return sitemapUrl;
      }
    }
  } catch (error) {}

  // Step 2: Try standard sitemap locations
  // Per sitemaps.org protocol, these are the conventional locations
  const standardLocations = [
    `${baseUrl}/sitemap.xml`,
    `${baseUrl}/sitemap_index.xml`,
  ];

  for (const url of standardLocations) {
    try {
      const response = await fetch(url, { method: "HEAD" });
      if (response.ok) {
        return url;
      }
    } catch {
      // Continue to next location
    }
  }

  return null;
}

/**
 * Fetches and parses a sitemap.xml file to extract page paths
 *
 * @param baseUrl - The base URL of the website
 * @returns Array of page paths (e.g., ["/", "/about", "/contact"])
 * @remarks
 * - Uses discoverSitemap() to find the sitemap location
 * - Extracts <loc> tags per https://www.sitemaps.org/protocol.html
 * - Returns paths only (strips domain) to work with preview deployments
 * - Falls back to ["/"] (homepage only) if sitemap discovery/parsing fails
 */
async function getPagesFromSitemap(baseUrl: string): Promise<string[]> {
  try {
    // Discover sitemap location (checks robots.txt + standard locations)
    const sitemapUrl = await discoverSitemap(baseUrl);

    if (!sitemapUrl) {
      throw new Error("No sitemap found");
    }

    const response = await fetch(sitemapUrl);
    if (!response.ok) {
      throw new Error(`Failed to fetch sitemap: ${response.status}`);
    }

    const xml = await response.text();

    // Extract all <loc> tags from sitemap XML
    // Format: <loc>https://example.com/page</loc>
    const locMatches = xml.matchAll(/<loc>(.*?)<\/loc>/g);
    const pages: string[] = [];

    for (const match of locMatches) {
      const url = match[1];
      try {
        const parsed = new URL(url);
        // Extract path from sitemap URL (e.g., https://example.com/about -> /about)
        // Note: We extract paths regardless of domain because sitemaps often have
        // hardcoded production URLs even on preview deployments
        const path = parsed.pathname || "/";
        if (!pages.includes(path)) {
          pages.push(path);
        }
      } catch (error) {
        console.warn(`  Skipping invalid URL from sitemap: ${url}`);
      }
    }

    if (pages.length === 0) {
      throw new Error("No valid pages found in sitemap");
    }

    return pages;
  } catch (error) {
    // Graceful fallback: if sitemap discovery/parsing fails, check homepage only
    console.error(`Error fetching sitemap: ${(error as Error).message}`);
    console.error("Falling back to homepage only\n");
    return ["/"];
  }
}

/**
 * Crawls a single page and checks all links and images for accessibility
 *
 * @param path - The page path to crawl (e.g., "/about")
 * @remarks
 * - Fetches the page HTML
 * - Extracts all href attributes from links
 * - Extracts all src attributes from images
 * - Checks each unique URL and records broken links/images in global results
 * - Skips anchors (#), javascript:, mailto:, tel: links
 * - Skips data: URIs and SVG sprite references for images
 */
async function crawlPage(path: string): Promise<void> {
  const pageUrl = new URL(path, BASE_URL).href;

  try {
    const response = await fetch(pageUrl);
    if (!response.ok) {
      console.error(`  Failed to fetch page: ${response.status}`);
      return;
    }

    const html = await response.text();
    results.pagesCrawled++;

    // Extract links
    const linkMatches = html.matchAll(/href=["']([^"']+)["']/g);
    for (const match of linkMatches) {
      const href = match[1];

      // Skip anchors, javascript, mailto, tel
      if (
        href.startsWith("#") ||
        href.startsWith("javascript:") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:")
      ) {
        continue;
      }

      const fullUrl = resolveUrl(href, pageUrl);
      if (!fullUrl || results.checkedLinks.has(fullUrl)) continue;

      results.checkedLinks.add(fullUrl);
      const isInternal = isInternalUrl(fullUrl);

      const { ok, status } = await checkUrl(fullUrl);

      if (!ok) {
        results.brokenLinks.push({
          page: path,
          url: href,
          fullUrl,
          status,
          isInternal,
        });
      }
    }

    // Extract images
    const imgMatches = html.matchAll(/src=["']([^"']+)["']/g);
    for (const match of imgMatches) {
      const src = match[1];

      // Skip data URIs and SVG sprites
      if (src.startsWith("data:") || src.startsWith("#")) continue;

      const fullUrl = resolveUrl(src, pageUrl);
      if (!fullUrl || results.checkedImages.has(fullUrl)) continue;

      results.checkedImages.add(fullUrl);

      const { ok, status } = await checkUrl(fullUrl);

      if (!ok) {
        results.missingImages.push({
          page: path,
          src,
          fullUrl,
          status,
        });
      }
    }
  } catch (error) {
    console.error(`  Error crawling ${path}: ${(error as Error).message}`);
  }
}

/**
 * Generates a markdown report from the collected results
 *
 * @returns Formatted markdown string with broken links, missing images, and summary statistics
 * @remarks
 * Report structure:
 * - Internal broken links (errors - cause CI failure)
 * - Missing images (errors - cause CI failure)
 * - External broken links (warnings - informational only)
 * - Summary table with crawl statistics
 */
function generateMarkdownReport(): string {
  const internalBroken = results.brokenLinks.filter((l) => l.isInternal);
  const externalBroken = results.brokenLinks.filter((l) => !l.isInternal);

  let report = `## 🔗 Link Checker Results\n\n`;

  // Summary
  const hasErrors =
    internalBroken.length > 0 || results.missingImages.length > 0;
  const hasWarnings = externalBroken.length > 0;

  if (!hasErrors && !hasWarnings) {
    report += `### ✅ All Clear!\n\n`;
    report += `No broken links or missing images found.\n\n`;
  }

  // Internal broken links (errors)
  if (internalBroken.length > 0) {
    report += `### ❌ Broken Internal Links (${internalBroken.length} found)\n\n`;
    report += `| Page | Broken Link | Status |\n`;
    report += `|------|-------------|--------|\n`;
    for (const link of internalBroken) {
      report += `| ${link.page} | \`${link.url}\` | ${link.status} |\n`;
    }
    report += `\n`;
  }

  // Missing images (errors)
  if (results.missingImages.length > 0) {
    report += `### ❌ Missing Images (${results.missingImages.length} found)\n\n`;
    report += `| Page | Image Source | Status |\n`;
    report += `|------|--------------|--------|\n`;
    for (const img of results.missingImages) {
      report += `| ${img.page} | \`${img.src}\` | ${img.status} |\n`;
    }
    report += `\n`;
  }

  // External broken links (warnings)
  if (externalBroken.length > 0) {
    report += `### ⚠️ Broken External Links (${externalBroken.length} found)\n\n`;
    report += `| Page | Broken Link | Status |\n`;
    report += `|------|-------------|--------|\n`;
    for (const link of externalBroken) {
      report += `| ${link.page} | \`${link.url}\` | ${link.status} |\n`;
    }
    report += `\n`;
  }

  // Stats - table format like Lighthouse CI
  report += `### 📊 Summary\n\n`;
  report += `| Metric | Count |\n`;
  report += `|--------|-------|\n`;
  report += `| **Pages crawled** | ${results.pagesCrawled} |\n`;
  report += `| **Links checked** | ${results.checkedLinks.size} |\n`;
  report += `| **Images checked** | ${results.checkedImages.size} |\n`;
  report += `| **Internal errors** | ${internalBroken.length + results.missingImages.length} |\n`;
  report += `| **External warnings** | ${externalBroken.length} |\n`;

  return report;
}

/**
 * Main entry point for the link checker script
 *
 * @remarks
 * Workflow:
 * 1. Discovers pages from sitemap.xml
 * 2. Crawls each page and checks all links/images
 * 3. Generates markdown report
 * 4. Writes report to link-checker-report.md
 * 5. Exits with code 1 if any broken links or missing images found
 */
async function main(): Promise<void> {
  // Fetch pages from sitemap
  const pages = await getPagesFromSitemap(BASE_URL!);

  for (const page of pages) {
    await crawlPage(page);
  }

  const report = generateMarkdownReport();

  // Output report to stdout

  // Write report to file for GitHub Actions
  fs.writeFileSync("link-checker-report.md", report);

  // Exit with error if ANY broken links or missing images found
  if (results.brokenLinks.length > 0 || results.missingImages.length > 0) {
    console.error("\n❌ Found broken links or missing images!");
    process.exit(1);
  }

  process.exit(0);
}

main();
