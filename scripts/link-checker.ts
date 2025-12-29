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
import * as fs from "fs"

declare const process: {
  argv: string[]
  exit: (code: number) => never
}


interface BrokenLink {
  page: string
  url: string
  fullUrl: string
  status: number | string
  isInternal: boolean
}

interface MissingImage {
  page: string
  src: string
  fullUrl: string
  status: number | string
}

interface Results {
  brokenLinks: BrokenLink[]
  missingImages: MissingImage[]
  checkedLinks: Set<string>
  checkedImages: Set<string>
  pagesCrawled: number
}

interface CheckUrlResult {
  ok: boolean
  status: number | string
}

const BASE_URL: string | undefined = process.argv[2]

if (!BASE_URL) {
  console.error("Usage: npx tsx scripts/link-checker.ts <base-url>")
  process.exit(1)
}

const results: Results = {
  brokenLinks: [],
  missingImages: [],
  checkedLinks: new Set(),
  checkedImages: new Set(),
  pagesCrawled: 0,
}

/**
 * URL Health Check
 * Checks if a URL is accessible (returns 2xx status code)
 */
async function checkUrl(url: string): Promise<CheckUrlResult> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)

    const response = await fetch(url, {
      method: "HEAD",
      signal: controller.signal,
      redirect: "follow",
    })

    clearTimeout(timeout)
    return { ok: response.ok, status: response.status }
  } catch (error) {
    return {
      ok: false,
      status: (error as Error).name === "AbortError" ? "Timeout" : "Connection failed",
    }
  }
}

/**
 * Internal URL Validator
 * Determines if a URL belongs to the same domain as the base URL
 */
function isInternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url, BASE_URL)
    const base = new URL(BASE_URL!)
    return parsed.hostname === base.hostname
  } catch {
    return false
  }
}

/**
 * URL Resolver
 * Resolves relative URLs to absolute URLs
 */
function resolveUrl(href: string, pageUrl: string): string | null {
  try {
    return new URL(href, pageUrl).href
  } catch {
    return null
  }
}

/**
 * ============================================================================
 * Sitemap Discovery Logic
 * ============================================================================
 * It follows web standards for discovering sitemaps:
 * 1. Check robots.txt for Sitemap directive
 * 2. Try standard sitemap locations
 * 3. Return null if not found (caller handles fallback)
 * ============================================================================
 */
async function discoverSitemap(baseUrl: string): Promise<string | null> {
  // Step 1: Check robots.txt for Sitemap directive
  // Many sites declare their sitemap location in robots.txt following the standard:
  // https://www.robotstxt.org/robotstxt.html
  try {
    const robotsUrl = `${baseUrl}/robots.txt`
    console.log(`Checking robots.txt: ${robotsUrl}`)

    const response = await fetch(robotsUrl)
    if (response.ok) {
      const robotsTxt = await response.text()

      // Look for "Sitemap: <url>" directive (case-insensitive)
      const sitemapMatch = robotsTxt.match(/Sitemap:\s*(.+)/i)
      if (sitemapMatch) {
        const sitemapUrl = sitemapMatch[1].trim()
        console.log(`  Found sitemap in robots.txt: ${sitemapUrl}`)
        return sitemapUrl
      }
    }
  } catch (error) {
    console.log(`  robots.txt not found or inaccessible`)
  }

  // Step 2: Try standard sitemap locations
  // Per sitemaps.org protocol, these are the conventional locations
  const standardLocations = [`${baseUrl}/sitemap.xml`, `${baseUrl}/sitemap_index.xml`]

  console.log(`Trying standard sitemap locations...`)
  for (const url of standardLocations) {
    try {
      const response = await fetch(url, { method: "HEAD" })
      if (response.ok) {
        console.log(`  Found sitemap at: ${url}`)
        return url
      }
    } catch {
      // Continue to next location
    }
  }

  console.log(`  No sitemap found at standard locations`)
  return null
}

/**
 * ============================================================================
 * Sitemap Parser
 * ============================================================================
 * Fetches and parses a sitemap.xml file to extract page URLs.
 * Supports standard sitemap format per https://www.sitemaps.org/protocol.html
 * ============================================================================
 */
async function getPagesFromSitemap(baseUrl: string): Promise<string[]> {
  try {
    // Discover sitemap location (checks robots.txt + standard locations)
    const sitemapUrl = await discoverSitemap(baseUrl)

    if (!sitemapUrl) {
      throw new Error("No sitemap found")
    }

    console.log(`Fetching sitemap from: ${sitemapUrl}`)
    const response = await fetch(sitemapUrl)
    if (!response.ok) {
      throw new Error(`Failed to fetch sitemap: ${response.status}`)
    }

    const xml = await response.text()

    // Extract all <loc> tags from sitemap XML
    // Format: <loc>https://example.com/page</loc>
    const locMatches = xml.matchAll(/<loc>(.*?)<\/loc>/g)
    const pages: string[] = []

    for (const match of locMatches) {
      const url = match[1]
      try {
        const parsed = new URL(url)
        // Extract path from sitemap URL (e.g., https://example.com/about -> /about)
        // Note: We extract paths regardless of domain because sitemaps often have
        // hardcoded production URLs even on preview deployments
        const path = parsed.pathname || "/"
        if (!pages.includes(path)) {
          pages.push(path)
        }
      } catch (error) {
        console.warn(`  Skipping invalid URL from sitemap: ${url}`)
      }
    }

    if (pages.length === 0) {
      throw new Error("No valid pages found in sitemap")
    }

    console.log(`Found ${pages.length} pages in sitemap\n`)
    return pages
  } catch (error) {
    // Graceful fallback: if sitemap discovery/parsing fails, check homepage only
    console.error(`Error fetching sitemap: ${(error as Error).message}`)
    console.error("Falling back to homepage only\n")
    return ["/"]
  }
}

async function crawlPage(path: string): Promise<void> {
  const pageUrl = new URL(path, BASE_URL).href
  console.log(`Crawling: ${pageUrl}`)

  try {
    const response = await fetch(pageUrl)
    if (!response.ok) {
      console.error(`  Failed to fetch page: ${response.status}`)
      return
    }

    const html = await response.text()
    results.pagesCrawled++

    // Extract links
    const linkMatches = html.matchAll(/href=["']([^"']+)["']/g)
    for (const match of linkMatches) {
      const href = match[1]

      // Skip anchors, javascript, mailto, tel
      if (
        href.startsWith("#") ||
        href.startsWith("javascript:") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:")
      ) {
        continue
      }

      const fullUrl = resolveUrl(href, pageUrl)
      if (!fullUrl || results.checkedLinks.has(fullUrl)) continue

      results.checkedLinks.add(fullUrl)
      const isInternal = isInternalUrl(fullUrl)

      const { ok, status } = await checkUrl(fullUrl)

      if (!ok) {
        results.brokenLinks.push({
          page: path,
          url: href,
          fullUrl,
          status,
          isInternal,
        })
      }
    }

    // Extract images
    const imgMatches = html.matchAll(/src=["']([^"']+)["']/g)
    for (const match of imgMatches) {
      const src = match[1]

      // Skip data URIs and SVG sprites
      if (src.startsWith("data:") || src.startsWith("#")) continue

      const fullUrl = resolveUrl(src, pageUrl)
      if (!fullUrl || results.checkedImages.has(fullUrl)) continue

      results.checkedImages.add(fullUrl)

      const { ok, status } = await checkUrl(fullUrl)

      if (!ok) {
        results.missingImages.push({
          page: path,
          src,
          fullUrl,
          status,
        })
      }
    }
  } catch (error) {
    console.error(`  Error crawling ${path}: ${(error as Error).message}`)
  }
}

function generateMarkdownReport(): string {
  const internalBroken = results.brokenLinks.filter(l => l.isInternal)
  const externalBroken = results.brokenLinks.filter(l => !l.isInternal)

  let report = `## 🔗 Link Checker Results\n\n`

  // Summary
  const hasErrors = internalBroken.length > 0 || results.missingImages.length > 0
  const hasWarnings = externalBroken.length > 0

  if (!hasErrors && !hasWarnings) {
    report += `### ✅ All Clear!\n\n`
    report += `No broken links or missing images found.\n\n`
  }

  // Internal broken links (errors)
  if (internalBroken.length > 0) {
    report += `### ❌ Broken Internal Links (${internalBroken.length} found)\n\n`
    report += `| Page | Broken Link | Status |\n`
    report += `|------|-------------|--------|\n`
    for (const link of internalBroken) {
      report += `| ${link.page} | \`${link.url}\` | ${link.status} |\n`
    }
    report += `\n`
  }

  // Missing images (errors)
  if (results.missingImages.length > 0) {
    report += `### ❌ Missing Images (${results.missingImages.length} found)\n\n`
    report += `| Page | Image Source | Status |\n`
    report += `|------|--------------|--------|\n`
    for (const img of results.missingImages) {
      report += `| ${img.page} | \`${img.src}\` | ${img.status} |\n`
    }
    report += `\n`
  }

  // External broken links (warnings)
  if (externalBroken.length > 0) {
    report += `### ⚠️ Broken External Links (${externalBroken.length} found)\n\n`
    report += `| Page | Broken Link | Status |\n`
    report += `|------|-------------|--------|\n`
    for (const link of externalBroken) {
      report += `| ${link.page} | \`${link.url}\` | ${link.status} |\n`
    }
    report += `\n`
  }

  // Stats - table format like Lighthouse CI
  report += `### 📊 Summary\n\n`
  report += `| Metric | Count |\n`
  report += `|--------|-------|\n`
  report += `| **Pages crawled** | ${results.pagesCrawled} |\n`
  report += `| **Links checked** | ${results.checkedLinks.size} |\n`
  report += `| **Images checked** | ${results.checkedImages.size} |\n`
  report += `| **Internal errors** | ${internalBroken.length + results.missingImages.length} |\n`
  report += `| **External warnings** | ${externalBroken.length} |\n`

  return report
}

async function main(): Promise<void> {
  console.log(`\n🔗 Link Checker starting...`)
  console.log(`Base URL: ${BASE_URL}\n`)

  // Fetch pages from sitemap
  const pages = await getPagesFromSitemap(BASE_URL!)

  for (const page of pages) {
    await crawlPage(page)
  }

  const report = generateMarkdownReport()

  // Output report to stdout
  console.log("\n" + "=".repeat(60) + "\n")
  console.log(report)

  // Write report to file for GitHub Actions
  fs.writeFileSync("link-checker-report.md", report)

  // Exit with error if ANY broken links or missing images found
  if (results.brokenLinks.length > 0 || results.missingImages.length > 0) {
    console.error("\n❌ Found broken links or missing images!")
    process.exit(1)
  }

  console.log("\n✅ All links and images are valid!")
  process.exit(0)
}

main()
