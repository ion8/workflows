#!/usr/bin/env node
/**
 * AutoMaintain PR Comment Fetcher Script
 * Fetch PR Comment URLs Script
 * Fetches comments from a GitHub PR and extracts URLs for Link Checker and Lighthouse comments.
 *
 * Usage: node scripts/fetch-pr-comments.js <repo-owner> <repo-name> <pr-number>
 * Example: node scripts/fetch-pr-comments.js ion8 efficient.legal 50
 *
 * Environment variables required:
 * - GITHUB_TOKEN: GitHub API token for authentication
 *
 * Output: Writes comment-urls.json with URLs to the Link Checker and Lighthouse comments
 */

const fs = require('fs');
const https = require('https');

// Comment markers that identify the results in PR comments
const LINK_CHECKER_MARKER = '## 🔗 Link Checker Results';
const LIGHTHOUSE_MARKER = '## 🚦 Lighthouse CI Results';

// Parse command line arguments
const [owner, repo, prNumber] = process.argv.slice(2);

if (!owner || !repo || !prNumber) {
  console.error('Usage: node scripts/fetch-pr-comments.js <repo-owner> <repo-name> <pr-number>');
  console.error('Example: node scripts/fetch-pr-comments.js ion8 efficient.legal 50');
  process.exit(1);
}

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
if (!GITHUB_TOKEN) {
  console.error('Error: GITHUB_TOKEN environment variable is required');
  process.exit(1);
}

/**
 * Make an HTTPS request to GitHub API
 * @param {string} path - API path
 * @returns {Promise<any>} - Parsed JSON response
 */
function githubRequest(path) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.github.com',
      path: path,
      method: 'GET',
      headers: {
        'User-Agent': 'AutoMaintain-Bot',
        'Authorization': `Bearer ${GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(JSON.parse(data));
        } else {
          reject(new Error(`GitHub API request failed: ${res.statusCode} ${data}`));
        }
      });
    });

    req.on('error', reject);
    req.end();
  });
}

/**
 * Extract comment URL by marker
 * @param {Array} comments - Array of comment objects from GitHub API
 * @param {string} marker - The marker string to search for
 * @returns {string|null} - The comment html_url or null if not found
 */
function extractCommentUrlByMarker(comments, marker) {
  const comment = comments.find(c => c.body.startsWith(marker));
  return comment ? comment.html_url : null;
}

async function main() {
  console.log(`Fetching comments for PR #${prNumber} in ${owner}/${repo}...`);

  try {
    // Fetch PR comments
    const comments = await githubRequest(`/repos/${owner}/${repo}/issues/${prNumber}/comments`);
    console.log(`Found ${comments.length} comments`);

    // Extract comment URLs
    const linkCheckerUrl = extractCommentUrlByMarker(comments, LINK_CHECKER_MARKER);
    const lighthouseUrl = extractCommentUrlByMarker(comments, LIGHTHOUSE_MARKER);

    if (!linkCheckerUrl) {
      console.warn('⚠ Link Checker comment not found in PR');
    } else {
      console.log('✓ Link Checker comment found');
    }

    if (!lighthouseUrl) {
      console.warn('⚠ Lighthouse comment not found in PR');
    } else {
      console.log('✓ Lighthouse comment found');
    }

    // Write URLs to JSON file
    const output = {
      linkCheckerUrl: linkCheckerUrl || null,
      lighthouseUrl: lighthouseUrl || null
    };

    fs.writeFileSync('comment-urls.json', JSON.stringify(output, null, 2));
    console.log('\n✓ Comment URLs written to comment-urls.json');

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
