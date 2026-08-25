import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { Client } from '../rdc/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../rdc/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.dirname(here);
const launcher = path.join(repo, 'rdc', 'start-rdc-observed-mcp.cmd');
const userHome = process.env.USERPROFILE;
const transport = new StdioClientTransport({ command: 'cmd.exe', args: ['/d', '/c', launcher], stderr: 'pipe' });
const client = new Client({ name: 'rdc-serena-fs-guard-smoke', version: '1.0.0' });

try {
  await client.connect(transport);
  const allowed = await client.callTool({ name: 'list_directory', arguments: { path: userHome, depth: 1 } });
  if (allowed.isError) throw new Error('Allowed USERPROFILE path was rejected');

  const blocked = await client.callTool({ name: 'list_directory', arguments: { path: 'C:\\Windows', depth: 1 } });
  const blockedText = blocked.content?.map((c) => c.type === 'text' ? c.text : '').join('\n') ?? '';
  if (!blocked.isError && !/not allowed|outside|denied|access/i.test(blockedText)) {
    throw new Error('C:\\Windows was not blocked by allowedDirectories');
  }

  console.log('RDC_FILESYSTEM_GUARD_SMOKE_OK');
} finally {
  await client.close();
}
