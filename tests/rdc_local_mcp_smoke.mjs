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

  const resources = await client.listResources();
  const uiResources = (resources.resources ?? []).filter((resource) => String(resource.uri ?? '').startsWith('ui://desktop-commander/'));
  if (uiResources.length) throw new Error(`RDC UI resources still exposed: ${uiResources.map((resource) => resource.uri).join(', ')}`);
  const cachedUiRead = await client.readResource({ uri: 'ui://desktop-commander/file-preview' });
  if ((cachedUiRead.contents ?? []).length) throw new Error('cached RDC UI resource read was not neutralized by Bridge');

  const readResult = await client.callTool({
    name: 'read_file',
    arguments: { path: path.join(repo, 'README.md'), offset: 0, length: 3 },
  });
  if (readResult.structuredContent !== undefined) throw new Error('read_file still exposes structuredContent through Bridge');
  const readMeta = readResult._meta ?? {};
  if (readMeta['ui/resourceUri'] || readMeta['openai/outputTemplate'] || readMeta.ui) throw new Error('read_file still exposes UI result metadata');

  const result = await client.callTool({ name: 'get_config', arguments: {} });
  if (result.structuredContent !== undefined) throw new Error('get_config structuredContent was not stripped by Bridge');
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
