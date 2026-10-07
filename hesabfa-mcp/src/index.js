import { createMcpExpressApp } from '@modelcontextprotocol/express';
import { toNodeHandler } from '@modelcontextprotocol/node';
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { randomUUID } from 'node:crypto';
import { getUserLogs, userLogStatus } from './user-logs.js';

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


async function runGoldiranImport14050712() {
  if (process.env.RUN_GOLDIRAN_IMPORT_14050712 !== '1') return;
  const reference = 'GLC-1405-07-12-10PCS';
  const date = '2026-10-04 00:00:00';
  const contactCode = '000070';

  const norm = (v) => String(v || '').toLowerCase()
    .replace(/تلویزیون|یخچال|ساید|جی\\s*پلاس/g, '')
    .replace(/[^a-z0-9]/g, '').replace(/^gtv/, '').replace(/^gss/, '');

  async function allItems() {
    const rows = [];
    let skip = 0, total = null;
    while (true) {
      const page = await hesabfaRequest('item/getitems', { queryInfo: { Take: 100, Skip: skip } });
      const list = Array.isArray(page?.List) ? page.List : [];
      if (total === null) total = Number(page?.TotalCount || 0);
      rows.push(...list); skip += list.length;
      if (!list.length || skip >= total) break;
    }
    if (total !== null && rows.length !== total) throw new Error('item pagination incomplete');
    return rows;
  }

  function exact(items, model) {
    const key = norm(model);
    const found = items.filter((x) =>
      [x?.Name, x?.PurchasesTitle, x?.SalesTitle, x?.ProductCode].some((v) => norm(v) === key));
    if (found.length > 1) throw new Error('ambiguous item ' + model);
    return found[0] || null;
  }

  async function ensureItem(model, payload) {
    let found = exact(await allItems(), model);
    if (found) return { item: found, created: false };
    const saved = await hesabfaRequest('item/save', { item: payload });
    found = exact(await allItems(), model);
    if (!found && saved?.Code) found = saved;
    if (!found?.Code) throw new Error('item create not verified ' + model);
    return { item: found, created: true };
  }

  async function existingInvoice() {
    let skip = 0, total = null, hit = null;
    while (true) {
      const page = await hesabfaRequest('invoice/getinvoices',
        { type: 1, queryInfo: { Take: 50, Skip: skip } });
      const list = Array.isArray(page?.List) ? page.List : [];
      if (total === null) total = Number(page?.TotalCount || 0);
      for (const x of list) {
        if (String(x?.Reference || '') === reference && String(x?.ContactCode || '') === contactCode) {
          if (hit) throw new Error('duplicate reference already exists');
          hit = x;
        }
      }
      skip += list.length;
      if (!list.length || skip >= total) break;
    }
    return hit;
  }

  console.log('GOLDIRAN_IMPORT_14050712 START');

  const current = await allItems();
  const tv65 = exact(current, 'GTV-65SU789N');
  if (!tv65?.Code) throw new Error('65SU789N not found');

  const tv55 = await ensureItem('GTV-55SU789NZ', {
    name: '55 SU 789 NZ تلویزیون جی پلاس', itemType: 0, productCode: 'GTV-55SU789NZ',
    unit: 'عدد', active: true, buyPrice: 1116720000, sellPrice: 1188000000,
    purchasesTitle: '55 SU 789 NZ تلویزیون جی پلاس',
    salesTitle: '55 SU 789 NZ تلویزیون جی پلاس'
  });
  const side = await ensureItem('GSS-R9515NS', {
    name: 'R 9515 NS ساید جی پلاس', itemType: 0, productCode: 'GSS-R9515NS',
    unit: 'عدد', active: true, buyPrice: 2143200000, sellPrice: 2280000000,
    purchasesTitle: 'R 9515 NS ساید جی پلاس',
    salesTitle: 'R 9515 NS ساید جی پلاس'
  });

  const lines = {
    side: { RowNumber: 0, ItemCode: String(side.item.Code), Description: 'GSS-R9515NS ساید جی پلاس',
      Quantity: 2, UnitPrice: 2280000000, Discount: 273600000, Tax: 0 },
    tv55: { RowNumber: 1, ItemCode: String(tv55.item.Code), Description: 'GTV-55SU789NZ تلویزیون جی پلاس',
      Quantity: 5, UnitPrice: 1188000000, Discount: 356400000, Tax: 0 },
    tv65: { RowNumber: 2, ItemCode: String(tv65.Code), Description: 'GTV-65SU789N تلویزیون جی پلاس',
      Quantity: 3, UnitPrice: 1460000000, Discount: 262800000, Tax: 0 }
  };

  let old = await existingInvoice();
  let invoiceNumber = old?.Number ? String(old.Number) : '';
  let invoiceCreated = false;
  if (!invoiceNumber) {
    const saved = await hesabfaRequest('invoice/save', {
      requestUniqueId: '6b5f45b0-30d2-4e71-8a36-140507120010',
      invoice: {
        Number: null, InvoiceType: 1, ContactCode: contactCode, ContactTitle: 'صنایع گلدایران',
        Date: date, DueDate: date, Reference: reference, Status: 1, Tag: 'GLC-1405-07-12',
        InvoiceItems: [lines.side, lines.tv55, lines.tv65],
        Note: 'خرید صنایع گلدایران طبق حواله GLC مورخ 1405/07/12. دو ساید در انبار دانشگاه 8 و تلویزیون‌ها در فروشگاه پالیز تخلیه شده‌اند. هزینه تخلیه 3,000,000 تومان بوده و تا تعیین حساب پرداخت، در بدهی این فاکتور منظور نشده است.',
        Freight: 0, Currency: 'IRR', CurrencyRate: 1
      }
    });
    invoiceNumber = String(saved?.Number || '');
    if (!invoiceNumber) invoiceNumber = String((await existingInvoice())?.Number || '');
    if (!invoiceNumber) throw new Error('invoice save not verified');
    invoiceCreated = true;
  }

  const palizReceipt = await hesabfaRequest('invoice/SaveWarehouseReceipt', {
    deleteOldReceipts: true,
    receipt: { WarehouseCode: 11, InvoiceNumber: Number(invoiceNumber), InvoiceType: 1,
      Date: date, Items: [lines.tv55, lines.tv65] }
  });
  const daneshgahReceipt = await hesabfaRequest('invoice/SaveWarehouseReceipt', {
    deleteOldReceipts: false,
    receipt: { WarehouseCode: 15, InvoiceNumber: Number(invoiceNumber), InvoiceType: 1,
      Date: date, Items: [lines.side] }
  });

  const verified = await hesabfaRequest('invoice/get', { number: Number(invoiceNumber), type: 1 });
  console.log('GOLDIRAN_IMPORT_14050712 RESULT ' + JSON.stringify({
    ok: true, invoiceNumber, invoiceCreated,
    itemCodes: { side: String(side.item.Code), tv55: String(tv55.item.Code), tv65: String(tv65.Code) },
    itemsCreated: { side: side.created, tv55: tv55.created },
    goodsNetIRR: 13987200000, unloadingIRRNotPosted: 30000000,
    payableIRR: Number(verified?.Payable || 0),
    receipts: {
      paliz: String(palizReceipt?.Number || ''),
      daneshgah8: String(daneshgahReceipt?.Number || '')
    }
  }));
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

const writeAnnotations = {
  readOnlyHint: false,
  destructiveHint: false,
  idempotentHint: false,
  openWorldHint: false
};

const destructiveAnnotations = {
  readOnlyHint: false,
  destructiveHint: true,
  idempotentHint: false,
  openWorldHint: false
};

async function hesabfaWrite(method, data, requestUniqueId) {
  const id = requestUniqueId || randomUUID();
  try {
    const result = await hesabfaRequest(method, { requestUniqueId: id, ...data });
    return { requestUniqueId: id, result };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const wrapped = new Error(`${message} [requestUniqueId=${id}]`);
    throw wrapped;
  }
}

function buildServer() {
  const server = new McpServer({
    name: 'hesabfa-readonly',
    version: '1.1.0'
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

  server.registerTool('hesabfa_user_logs_status', {
    title: 'Hesabfa user log connection status',
    description: 'Check whether the separate Hesabfa website session for user activity logs is configured. This does not validate the live session. Never ask for credentials in chat.',
    annotations: readAnnotations
  }, async () => toolResult(userLogStatus()));

  server.registerTool('hesabfa_user_logs', {
    title: 'Hesabfa user activity logs',
    description: 'Read actual user activity logs, including timestamp, user, action, title and description. Requires the separately configured website session. Dates must be Gregorian YYYY-MM-DD or ISO timestamps; date-only and unzoned timestamps use Iran time. Maximum 31 days per request. Follow nextSkip until null for a complete report. Preserve original timestamps. Authentication errors never mean there was no activity. Never pass or request cookies or credentials as tool inputs.',
    inputSchema: z.object({
      start: z.string().min(10).max(40),
      end: z.string().min(10).max(40),
      userId: z.string().max(200).optional().default(''),
      skip: z.number().int().min(0).max(1000000).optional().default(0),
      take: z.number().int().min(1).max(100).optional().default(50)
    }).strict(),
    annotations: readAnnotations
  }, async (args) => {
    try {
      const result = await enqueueApiCall(() => getUserLogs(args));
      // Preserve complete rows and pagination; the generic helper truncates JSON.
      return { content: [{ type: 'text', text: JSON.stringify(result) }], structuredContent: result };
    } catch (error) {
      return toolError(new Error(`${error.code || 'USER_LOG_ERROR'}: ${error.message}`));
    }
  });

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


  // ---- Write tools ----
  // These tools intentionally require confirm=true. Hesabfa requestUniqueId is
  // attached to every mutation to reduce duplicate writes on retries.

  server.registerTool('hesabfa_save_invoice', {
    title: 'Save Hesabfa invoice',
    description: 'Create or update a Hesabfa invoice. Use invoiceType 0 for sale and 1 for purchase. Dates must be Gregorian. Amounts must use the connected business base currency (IRR here). Only call after the user has clearly instructed the write.',
    inputSchema: z.object({
      invoice: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ invoice, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/save', { invoice }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_invoice_payment', {
    title: 'Save Hesabfa invoice payment',
    description: 'Record a payment/receipt against an existing invoice. Pass the invoice number/type plus payment fields supported by Hesabfa such as bankCode, cashCode, pettyCashCode, contactCode, accountPath, date, amount, transactionNumber, project, description, transactionFee, currency and currencyRate.',
    inputSchema: z.object({
      payment: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ payment, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/savePayment', payment, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_invoice_warehouse_receipt', {
    title: 'Save Hesabfa invoice warehouse receipt',
    description: 'Create warehouse receipt/issue records linked to a purchase or sales invoice. If invoice items are split across warehouses, call once per warehouse. Set deleteOldReceipts carefully because true replaces prior warehouse receipts for that invoice.',
    inputSchema: z.object({
      receipt: z.record(z.string(), z.unknown()),
      deleteOldReceipts: z.boolean().optional().default(false),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ receipt, deleteOldReceipts, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/SaveWarehouseReceipt', { deleteOldReceipts, receipt }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_warehouse_receipt', {
    title: 'Save Hesabfa warehouse receipt',
    description: 'Create or edit an independent warehouse receipt, issue, or transfer. Use receiving=true for receipt and receiving=false for issue; destinationWarehouseCode is used for transfers.',
    inputSchema: z.object({
      receipt: z.record(z.string(), z.unknown()),
      deleteOldReceipts: z.boolean().optional().default(false),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ receipt, deleteOldReceipts, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('warehouse/save', { deleteOldReceipts, receipt }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_contact', {
    title: 'Save Hesabfa contact',
    description: 'Create or update a Hesabfa customer, supplier, employee, or other contact.',
    inputSchema: z.object({
      contact: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ contact, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('contact/save', { contact }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_item', {
    title: 'Save Hesabfa item',
    description: 'Create or update a Hesabfa item or service.',
    inputSchema: z.object({
      item: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ item, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('item/save', { item }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_receipt', {
    title: 'Save Hesabfa receipt or payment',
    description: 'Create or update a simple Hesabfa receive/pay voucher. Pass fields supported by receipt/save including type, contactCode, amount and the bank/cash/petty-cash destination/source.',
    inputSchema: z.object({
      receipt: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ receipt, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('receipt/save', receipt, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_save_receipt_detailed', {
    title: 'Save detailed Hesabfa receipt or payment',
    description: 'Create a detailed Hesabfa receive/pay voucher using receipt/save2, including accounting items and transaction legs.',
    inputSchema: z.object({
      receipt: z.record(z.string(), z.unknown()),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ receipt, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('receipt/save2', receipt, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_change_invoice_paid_status', {
    title: 'Change Hesabfa invoice paid status',
    description: 'Mark a confirmed invoice paid or unpaid.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      type: z.number().int(),
      paid: z.boolean(),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ number, type, paid, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/changePaidStatus', { number, type, paid }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_change_invoice_sent_status', {
    title: 'Change Hesabfa invoice sent status',
    description: 'Mark a confirmed invoice sent or not sent.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      type: z.number().int(),
      sent: z.boolean(),
      requestUniqueId: z.string().uuid().optional(),
      confirm: z.literal(true)
    }).strict(),
    annotations: writeAnnotations
  }, async ({ number, type, sent, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/changeSentStatus', { number, type, sent }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_delete_invoice', {
    title: 'Delete Hesabfa invoice',
    description: 'Permanently delete a Hesabfa invoice. Use only after the user explicitly asks to delete that exact invoice.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      type: z.number().int(),
      requestUniqueId: z.string().uuid().optional(),
      confirmDelete: z.literal(true)
    }).strict(),
    annotations: destructiveAnnotations
  }, async ({ number, type, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('invoice/delete', { number, type }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_delete_contact', {
    title: 'Delete Hesabfa contact',
    description: 'Permanently delete a Hesabfa contact by code. Use only after explicit user instruction.',
    inputSchema: z.object({
      code: z.union([z.string(), z.number()]),
      requestUniqueId: z.string().uuid().optional(),
      confirmDelete: z.literal(true)
    }).strict(),
    annotations: destructiveAnnotations
  }, async ({ code, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('contact/delete', { code }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_delete_item', {
    title: 'Delete Hesabfa item',
    description: 'Permanently delete a Hesabfa item/service by code. Use only after explicit user instruction.',
    inputSchema: z.object({
      code: z.union([z.string(), z.number()]),
      requestUniqueId: z.string().uuid().optional(),
      confirmDelete: z.literal(true)
    }).strict(),
    annotations: destructiveAnnotations
  }, async ({ code, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('item/delete', { code }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_delete_receipt', {
    title: 'Delete Hesabfa receipt',
    description: 'Permanently delete a Hesabfa receive/pay voucher by number and type. Use only after explicit user instruction.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      type: z.number().int(),
      requestUniqueId: z.string().uuid().optional(),
      confirmDelete: z.literal(true)
    }).strict(),
    annotations: destructiveAnnotations
  }, async ({ number, type, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('receipt/delete', { number, type }, requestUniqueId)); }
    catch (error) { return toolError(error); }
  });

  server.registerTool('hesabfa_delete_warehouse_receipt', {
    title: 'Delete Hesabfa warehouse receipt',
    description: 'Permanently delete a Hesabfa warehouse receipt/issue by number. Use only after explicit user instruction.',
    inputSchema: z.object({
      number: z.union([z.string(), z.number()]),
      requestUniqueId: z.string().uuid().optional(),
      confirmDelete: z.literal(true)
    }).strict(),
    annotations: destructiveAnnotations
  }, async ({ number, requestUniqueId }) => {
    try { return toolResult(await hesabfaWrite('warehouse/delete', { number }, requestUniqueId)); }
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

void runGoldiranImport14050712().catch((e) => console.log('GOLDIRAN_IMPORT_14050712 ERROR ' + String(e?.message || e)));\n\napp.listen(PORT, '0.0.0.0', () => {
  console.log(`Hesabfa read-only bridge listening on port ${PORT}`);
  console.log(`MCP enabled: ${MCP_ENABLED}`);
  console.log(`Hesabfa credentials configured: ${credentialsConfigured()}`);
  console.log(`Hesabfa user logs: ${userLogStatus().code}`);
});
