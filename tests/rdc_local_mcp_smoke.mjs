import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { Client } from '../rdc/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { StdioClientTransport } from '../rdc/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.dirname(here);
const launcher = path.join(repo, 'rdc', 'start-rdc-observed-mcp.cmd');
const userHome = process.env.USERPROFILE;

const transport = new StdioClientTransport({
  command: 'cmd.exe',
  args: ['/d', '/c', launcher],
  stderr: 'pipe',
});
let stderr = '';
transport.stderr?.on('data', (chunk) => { stderr += chunk.toString(); });
const client = new Client({ name: 'rdc-serena-modify-smoke', version: '1.0.0' });

try {
  await client.connect(transport);
  const listed = await client.listTools();
  const names = listed.tools.map((tool) => tool.name);
  if (!names.includes('get_config')) throw new Error('get_config not exposed');
  if (!names.includes('start_process')) throw new Error('start_process not exposed');
  const uiTools = listed.tools.filter((tool) => {
    const meta = tool._meta ?? {};
    return Boolean(meta['ui/resourceUri'] || meta['openai/outputTemplate'] || meta.ui);
  });
  if (uiTools.length) throw new Error(`RDC MCP UI previews still exposed: ${uiTools.map((tool) => tool.name).join(', ')}`);

  const result = await client.callTool({ name: 'get_config', arguments: {} });
  const text = result.content?.map((c) => c.type === 'text' ? c.text : '').join('\n') ?? '';
  const normalizedText = text.replace(/\\\\/g, '\\');
  if (!normalizedText.includes(userHome)) throw new Error(`allowedDirectories does not include ${userHome}`);
  if (!/telemetryEnabled[\"'\s:]+false/i.test(text)) throw new Error('telemetryEnabled is not false');

  console.log('RDC_LOCAL_MCP_SMOKE_OK');
  console.log(`tool_count=${names.length}`);
} finally {
  await client.close();
}

if (/device access|authenticating with remote|device verified|open.*browser/i.test(stderr)) {
  console.error(stderr);
  process.exit(2);
}
