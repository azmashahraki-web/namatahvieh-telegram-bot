import { createMcpExpressApp } from '@modelcontextprotocol/express';
import { toNodeHandler } from '@modelcontextprotocol/node';
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const PORT = Number(process.env.PORT || 3000);
const HESABFA_API_BASE = process.env.HESABFA_API_BASE || 'https://api.hesabfa.com/v1';
const MCP_ENABLED = String(process.env.MCP_ENABLED || 'false').toLowerCase() === 'true';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let requestTail = Promise.resolve();
let lastApiCallAt = 0;

function credentialsConfigured() {
  return Boolean(process.env.HESABFA_API_KEY && process.env.HESABFA_LOGIN_TOKEN);
}

function enqueueApiCall(fn) {
  const run = requestTail.then(async () => {
    const elapsed = Date.now() - lastApiCallAt;
    if (elapsed < 1100) await sleep(1100 - elapsed);
    lastApiCallAt = Date.now();
    return fn();
  });
  requestTail = run.catch(() => undefined);
  return run;
}

async function hesabfaRequest(method, data = {}) {
  if (!credentialsConfigured()) {
    throw new Error('Hesabfa credentials are not configured on the server.');
  }

  return enqueueApiCall(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(`${HESABFA_API_BASE}/${method}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey: process.env.HESABFA_API_KEY,
          loginToken: process.env.HESABFA_LOGIN_TOKEN,
          userId: '',
          password: '',
          ...data
        }),
        signal: controller.signal
      });

      const text = await response.text();
      let payload;
      try {
        payload = JSON.parse(text);
      } catch {
        throw new Error(`Hesabfa returned a non-JSON response (HTTP ${response.status}).`);
      }

      if (!response.ok) {
        throw new Error(`Hesabfa HTTP error ${response.status}.`);
      }

      if (payload?.Success === false || (!payload?.Success && payload?.ErrorCode)) {
        const code = payload?.ErrorCode ?? 'unknown';
        const message = payload?.ErrorMessage ? `: ${payload.ErrorMessage}` : '';
        throw new Error(`Hesabfa API error ${code}${message}`);
      }

      return payload?.Result ?? payload?.Data ?? payload;
    } finally {
      clearTimeout(timeout);
    }
  });
}

function toolResult(data) {
  const json = JSON.stringify(data, null, 2);
  const max = 50000;
  const text = json.length > max
    ? `${json.slice(0, max)}\n\n[Output truncated by bridge at ${max} characters.]`
    : json;
  return { content: [{ type: 'text', text }] };
}

function toolError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return { content: [{ type: 'text', text: message }], isError: true };
}

const readAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false
};

function buildServer() {
  const server = new McpServer({
    name: 'hesabfa-readonly',
    version: '1.0.0'
  });

  const noArgs = (name, title, description, method) => {
    server.registerTool(name, {
      title,
      description,
      annotations: readAnnotations
    }, async () => {
      try { return toolResult(await hesabfaRequest(method)); }
      catch (error) { return toolError(error); }
    });
  };

  noArgs('hesabfa_business_info', 'Hesabfa business info', 'Read basic information about the connected Hesabfa business.', 'setting/getBusinessInfo');
  noArgs('hesabfa_fiscal_year', 'Hesabfa fiscal year', 'Read the active fiscal year from Hesabfa.', 'setting/GetFiscalYear');
  noArgs('hesabfa_warehouses', 'Hesabfa warehouses', 'List warehouses in the connected Hesabfa business.', 'setting/GetWarehouses');
  noArgs('hesabfa_banks', 'Hesabfa banks', 'List bank and cash accounts available through Hesabfa.', 'setting/getBanks');
  noArgs('hesabfa_projects', 'Hesabfa projects', 'List projects defined in Hesabfa.', 'setting/getProjects');
  noArgs('hesabfa_salesmen', 'Hesabfa salespeople', 'List salespeople defined in Hesabfa.', 'setting/getSalesmen');
  noArgs('hesabfa_currency', 'Hesabfa currency', 'Read currency settings from Hesabfa.', 'setting/getCurrency');

  server.registerTool('hesabfa_item', {
    title: 'Get Hesabfa item',
    description: 'Read one item or service by its Hesabfa code.',
    inputSchema: z.object({ code: z.union([z.string(), z.number()]) }),
    annotations: readAnnotations
  }, async ({ code }) => {
    try { return toolResult(await hesabfaRequest('item/get', { code })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_item_by_barcode', {
    title: 'Get Hesabfa item by barcode',
    description: 'Read an item or service by barcode.',
    inputSchema: z.object({ barcode: z.string().min(1) }),
    annotations: readAnnotations
  }, async ({ barcode }) => {
    try { return toolResult(await hesabfaRequest('item/getByBarcode', { barcode })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_item_quantity', {
    title: 'Get Hesabfa stock quantity',
    description: 'Read stock quantities for item codes in a warehouse.',
    inputSchema: z.object({
      warehouseCode: z.union([z.string(), z.number()]),
      codes: z.array(z.union([z.string(), z.number()])).min(1).max(100)
    }),
    annotations: readAnnotations
  }, async ({ warehouseCode, codes }) => {
    try { return toolResult(await hesabfaRequest('item/GetQuantity', { warehouseCode, codes })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_invoice', {
    title: 'Get Hesabfa invoice',
    description: 'Read one invoice by number. Type defaults to 0 when omitted.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      type: z.number().int().optional().default(0)
    }),
    annotations: readAnnotations
  }, async ({ number, type }) => {
    try { return toolResult(await hesabfaRequest('invoice/get', { number, type })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_contact', {
    title: 'Get Hesabfa contact',
    description: 'Read one customer, supplier, or contact by Hesabfa code.',
    inputSchema: z.object({ code: z.union([z.string(), z.number()]) }),
    annotations: readAnnotations
  }, async ({ code }) => {
    try { return toolResult(await hesabfaRequest('contact/get', { code })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_list_items', {
    title: 'List Hesabfa items',
    description: 'Read a page/list of items and services. Pass Hesabfa queryInfo fields when filtering or paging; an empty object requests the API default page.',
    inputSchema: z.object({ queryInfo: z.record(z.string(), z.unknown()).optional().default({}) }),
    annotations: readAnnotations
  }, async ({ queryInfo }) => {
    try { return toolResult(await hesabfaRequest('item/getitems', { queryInfo })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_list_invoices', {
    title: 'List Hesabfa invoices',
    description: 'Read a page/list of invoices. Type defaults to 0. Pass Hesabfa queryInfo fields when filtering or paging.',
    inputSchema: z.object({
      type: z.number().int().optional().default(0),
      queryInfo: z.record(z.string(), z.unknown()).optional().default({})
    }),
    annotations: readAnnotations
  }, async ({ type, queryInfo }) => {
    try { return toolResult(await hesabfaRequest('invoice/getinvoices', { type, queryInfo })); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_list_contacts', {
    title: 'List Hesabfa contacts',
    description: 'Read a page/list of customers, suppliers, and other contacts. Pass Hesabfa queryInfo fields when filtering or paging.',
    inputSchema: z.object({ queryInfo: z.record(z.string(), z.unknown()).optional().default({}) }),
    annotations: readAnnotations
  }, async ({ queryInfo }) => {
    try { return toolResult(await hesabfaRequest('contact/getcontacts', { queryInfo })); }
    catch (error) { return toolError(error); }
  });

  return server;
}

const handler = createMcpHandler(buildServer);
const nodeHandler = toNodeHandler(handler);
const app = createMcpExpressApp({ host: '0.0.0.0' });

app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    mcpEnabled: MCP_ENABLED,
    hesabfaCredentialsConfigured: credentialsConfigured()
  });
});

app.all('/mcp', (req, res) => {
  if (!MCP_ENABLED) {
    return res.status(503).json({
      error: 'MCP endpoint is intentionally disabled until authentication is configured.'
    });
  }
  return void nodeHandler(req, res, req.body);
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Hesabfa read-only bridge listening on port ${PORT}`);
  console.log(`MCP enabled: ${MCP_ENABLED}`);
  console.log(`Hesabfa credentials configured: ${credentialsConfigured()}`);
});
