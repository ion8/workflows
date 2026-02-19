#!/usr/bin/env node
/**
 * Create Confluence Page Script
 * Creates a Confluence page with AutoMaintain report content.
 *
 * Usage: node scripts/create-confluence-page.js
 *
 * Environment variables required:
 * - CONFLUENCE_API_TOKEN: Atlassian API token
 * - CONFLUENCE_USER_EMAIL: Service account email
 * - CONFLUENCE_BASE_URL: Base URL for Confluence API
 * - CONFLUENCE_SPACE_ID: Space ID where the page will be created
 * - CONFLUENCE_PARENT_PAGE_ID: Parent page ID
 * - PR_NUMBER: PR number
 * - PR_TITLE: PR title
 * - PR_URL: Full URL to the PR
 * - MERGED_DATE: Date the PR was merged
 * - REPO_NAME: Repository name (e.g., "ion8/efficient.legal")
 * - REPO_URL: Full URL to the repository
 * - LINK_CHECKER_URL: URL to Link Checker comment on PR
 * - LIGHTHOUSE_URL: URL to Lighthouse comment on PR
 *
 * Input files required:
 * - scripts/confluence-report-template.html: Page template
 *
 * Output: Writes confluence-page-url.txt with the URL to the created page
 */

const fs = require('fs');
const https = require('https');
const { URL } = require('url');

// Required environment variables
const REQUIRED_ENV_VARS = [
  'CONFLUENCE_API_TOKEN',
  'CONFLUENCE_USER_EMAIL',
  'CONFLUENCE_BASE_URL',
  'CONFLUENCE_SPACE_ID',
  'CONFLUENCE_PARENT_PAGE_ID',
  'PR_NUMBER',
  'PR_TITLE',
  'PR_URL',
  'MERGED_DATE',
  'REPO_NAME',
  'REPO_URL',
  'LINK_CHECKER_URL',
  'LIGHTHOUSE_URL'
];

// Validate environment variables
const missingVars = REQUIRED_ENV_VARS.filter(v => !process.env[v]);
if (missingVars.length > 0) {
  console.error('Error: Missing required environment variables:');
  missingVars.forEach(v => console.error(`  - ${v}`));
  process.exit(1);
}

const {
  CONFLUENCE_API_TOKEN,
  CONFLUENCE_USER_EMAIL,
  CONFLUENCE_BASE_URL,
  CONFLUENCE_SPACE_ID,
  CONFLUENCE_PARENT_PAGE_ID,
  PR_NUMBER,
  PR_TITLE,
  PR_URL,
  MERGED_DATE,
  REPO_NAME,
  REPO_URL,
  LINK_CHECKER_URL,
  LIGHTHOUSE_URL
} = process.env;

/**
 * Make an HTTPS request to Confluence API
 * @param {string} method - HTTP method
 * @param {string} path - API path
 * @param {object|null} body - Request body (for POST/PUT)
 * @returns {Promise<any>} - Parsed JSON response
 */
function confluenceRequest(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, CONFLUENCE_BASE_URL);
    const auth = Buffer.from(`${CONFLUENCE_USER_EMAIL}:${CONFLUENCE_API_TOKEN}`).toString('base64');

    const options = {
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: method,
      headers: {
        'Authorization': `Basic ${auth}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            resolve(data);
          }
        } else {
          reject(new Error(`Confluence API request failed: ${res.statusCode} ${data}`));
        }
      });
    });

    req.on('error', reject);

    if (body) {
      req.write(JSON.stringify(body));
    }

    req.end();
  });
}

/**
 * Load and populate the page template
 * @returns {string} - HTML content for the page
 */
function generatePageContent() {
  // Read template
  const templatePath = __dirname + '/confluence-report-template.html';
  if (!fs.existsSync(templatePath)) {
    throw new Error(`Template not found: ${templatePath}`);
  }
  let template = fs.readFileSync(templatePath, 'utf8');

  // Extract repo name without org (e.g., "efficient.legal" from "ion8/efficient.legal")
  const repoShortName = REPO_NAME.split('/')[1] || REPO_NAME;

  // Generate title with [Draft] prefix
  const title = `[Draft] ${PR_TITLE} - ${repoShortName}`;

  // Replace placeholders
  const content = template
    .replace(/{{TITLE}}/g, title)
    .replace(/{{PR_NUMBER}}/g, PR_NUMBER)
    .replace(/{{PR_TITLE}}/g, PR_TITLE)
    .replace(/{{PR_URL}}/g, PR_URL)
    .replace(/{{MERGED_DATE}}/g, MERGED_DATE)
    .replace(/{{REPO_NAME}}/g, REPO_NAME)
    .replace(/{{REPO_URL}}/g, REPO_URL)
    .replace(/{{LINK_CHECKER_URL}}/g, LINK_CHECKER_URL)
    .replace(/{{LIGHTHOUSE_URL}}/g, LIGHTHOUSE_URL);

  return { title, content };
}

async function main() {
  console.log('Creating Confluence page...');

  try {
    // Generate page content
    const { title, content } = generatePageContent();
    console.log(`Title: ${title}`);

    // Create page via Confluence API
    const pageData = {
      spaceId: CONFLUENCE_SPACE_ID,
      status: 'current', // Published, not draft
      title: title,
      parentId: CONFLUENCE_PARENT_PAGE_ID,
      body: {
        representation: 'storage',
        value: content
      }
    };

    console.log('Sending request to Confluence API...');
    const response = await confluenceRequest('POST', '/wiki/api/v2/pages', pageData);

    // Extract page URL from response
    const pageUrl = response._links.base + response._links.webui;
    console.log(`✓ Page created successfully: ${pageUrl}`);

    // Write URL to file for workflow to use
    fs.writeFileSync('confluence-page-url.txt', pageUrl);
    console.log('✓ Page URL written to confluence-page-url.txt');

    // Output for GitHub Actions
    console.log(`\n::notice title=Confluence Page Created::${pageUrl}`);

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
