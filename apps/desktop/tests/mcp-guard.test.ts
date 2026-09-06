/** MCP spawn öncesi allowlist / araç / tampon. */

import { describe, expect, it } from 'vitest';

import { MCP_JSON_COMMANDS } from '@shared/settings';

import {
  MCP_COMMAND_ALLOWLIST,
  MCP_STDERR_CAP,
  MCP_STDOUT_BUFFER_CAP,
  appendMcpStderr,
  appendMcpStdout,
  encodeMcpStdioFrame,
  mcpListAdvanceCursor,
  mcpListCursorParam,
  mcpListNextCursor,
  mcpParseConcatenatedJson,
  mcpParseRpcMessages,
  mcpRpcErrorMessage,
  mcpServerRequestReply,
  mcpToolsFromListResult,
  mcpUniqueToolNames,
  filterSafeMcpArgs,
  isForbiddenMcpArg,
  mcpCommandAllowed,
  prepareMcpCall,
  prepareMcpServer,
  resolveMcpRpcId,
  sanitizeMcpToolArgs,
  sanitizeMcpToolName,
} from '../electron/host-tools/mcp-guard';

const enabled = {
  mcpEnabled: true,
  mcpServers: [
    {
      id: 'docs',
      command: 'npx',
      args: ['-y', '@upstash/context7-mcp'],
      allowedTools: ['query-docs'],
    },
  ],
};

describe('MCP guard', () => {
  it('docker ve cmd komut allowlist dışında', () => {
    expect(mcpCommandAllowed('npx')).toBe(true);
    expect(mcpCommandAllowed('bun.cmd')).toBe(true);
    expect(mcpCommandAllowed('uvx.cmd')).toBe(true);
    expect(mcpCommandAllowed('npx.bat')).toBe(true);
    expect(mcpCommandAllowed('python3')).toBe(true);
    expect(mcpCommandAllowed('pythonw.exe')).toBe(true);
    expect(mcpCommandAllowed('bunx')).toBe(true);
    expect(mcpCommandAllowed('uv')).toBe(true);
    expect(mcpCommandAllowed('npm.cmd')).toBe(true);
    expect(mcpCommandAllowed('pnpx.cmd')).toBe(true);
    expect(mcpCommandAllowed('pnpm.exe')).toBe(true);
    expect(mcpCommandAllowed('yarn.cmd')).toBe(true);
    expect(mcpCommandAllowed('node.cmd')).toBe(true);
    expect(mcpCommandAllowed('python.cmd')).toBe(true);
    expect(mcpCommandAllowed('C:\\\\Program Files\\\\nodejs\\\\npx.cmd')).toBe(true);
    expect(mcpCommandAllowed('\\\\evil\\\\share\\\\npx.cmd')).toBe(false);
    expect(mcpCommandAllowed('//evil/share/npx.cmd')).toBe(false);
    expect(mcpCommandAllowed('.\\\\npx.cmd')).toBe(false);
    expect(mcpCommandAllowed('C:\\\\foo\\\\..\\\\npx.cmd')).toBe(false);
    expect(mcpCommandAllowed('docker')).toBe(false);
    expect(mcpCommandAllowed('cmd.exe')).toBe(false);
    expect(mcpCommandAllowed('powershell')).toBe(false);
    expect(mcpCommandAllowed('npx\r\ncalc')).toBe(false);
    expect(mcpCommandAllowed('C:npx')).toBe(false);
    expect(mcpCommandAllowed('C:npx.cmd')).toBe(false);
    expect(mcpCommandAllowed('npx\tcalc')).toBe(false);
    expect([...MCP_COMMAND_ALLOWLIST].sort()).toEqual([...MCP_JSON_COMMANDS].sort());
  });

  it('npx -c / node -e / python -c ve inspect düşer, -y ve -m kalır', () => {
    expect(isForbiddenMcpArg('-y')).toBe(false);
    expect(isForbiddenMcpArg('-m')).toBe(false);
    expect(isForbiddenMcpArg('--isolated')).toBe(false);
    expect(isForbiddenMcpArg('-c')).toBe(true);
    expect(isForbiddenMcpArg('--call')).toBe(true);
    expect(isForbiddenMcpArg('-e')).toBe(true);
    expect(isForbiddenMcpArg('--eval')).toBe(true);
    expect(isForbiddenMcpArg('--node-options=--inspect')).toBe(true);
    expect(isForbiddenMcpArg('--inspect-brk')).toBe(true);
    expect(isForbiddenMcpArg('-r')).toBe(true);
    expect(isForbiddenMcpArg('--require')).toBe(true);
    expect(isForbiddenMcpArg('--import')).toBe(true);
    expect(isForbiddenMcpArg('--import=./evil.js')).toBe(true);
    expect(isForbiddenMcpArg('pkg;rm')).toBe(true);
    expect(isForbiddenMcpArg('pkg%PATH%')).toBe(true);
    expect(isForbiddenMcpArg('pkg!TEMP!')).toBe(true);
    expect(isForbiddenMcpArg('foo"bar')).toBe(true);
    expect(isForbiddenMcpArg('pkg\0x')).toBe(true);
    expect(isForbiddenMcpArg('pkg\tfoo')).toBe(true);
    expect(isForbiddenMcpArg('pkg\vfoo')).toBe(true);
    expect(filterSafeMcpArgs(['-y', 'pkg\tfoo', 'ok'])).toEqual(['-y', 'ok']);
    expect(isForbiddenMcpArg('../evil')).toBe(true);
    expect(filterSafeMcpArgs(['-y', '../evil', 'pkg'])).toEqual(['-y', 'pkg']);
    expect(filterSafeMcpArgs(['-y', '-c', 'calc', 'pkg'])).toEqual(['-y', 'pkg']);
    expect(filterSafeMcpArgs(['  -y  ', '  pkg  '])).toEqual(['-y', 'pkg']);
    expect(isForbiddenMcpArg('--preload')).toBe(true);
    expect(isForbiddenMcpArg('--inspect-port')).toBe(true);
    expect(isForbiddenMcpArg('--inspect-port=9229')).toBe(true);
    expect(isForbiddenMcpArg('-p')).toBe(true);
    expect(isForbiddenMcpArg('-p', 'npx')).toBe(false);
    expect(isForbiddenMcpArg('-p', 'node')).toBe(true);
    expect(filterSafeMcpArgs(['-y', '-p', 'pkg'], 'npx')).toEqual(['-y', '-p', 'pkg']);
    expect(isForbiddenMcpArg('-p', 'pnpx')).toBe(false);
    expect(filterSafeMcpArgs(['-p', 'code'], 'node')).toEqual([]);
    expect(isForbiddenMcpArg('-')).toBe(true);
    expect(isForbiddenMcpArg('--run')).toBe(true);
    expect(isForbiddenMcpArg('--run=dev')).toBe(true);
    expect(filterSafeMcpArgs(['-y', '-', 'pkg'])).toEqual(['-y', 'pkg']);
    expect(filterSafeMcpArgs(['--run', 'dev', 'pkg'], 'node')).toEqual(['pkg']);
    expect(isForbiddenMcpArg('run', 'npm')).toBe(true);
    expect(isForbiddenMcpArg('start', 'yarn.cmd')).toBe(true);
    expect(isForbiddenMcpArg('run', 'npx')).toBe(false);
    expect(filterSafeMcpArgs(['run', 'evil', 'pkg'], 'npm')).toEqual(['pkg']);
    expect(filterSafeMcpArgs(['start', 'pkg'], 'pnpm')).toEqual(['pkg']);
    expect(isForbiddenMcpArg('-i', 'python')).toBe(true);
    expect(isForbiddenMcpArg('-i', 'node')).toBe(true);
    expect(isForbiddenMcpArg('--interactive', 'python3')).toBe(true);
    expect(isForbiddenMcpArg('-i', 'uvx')).toBe(false);
    expect(isForbiddenMcpArg('--env-file')).toBe(true);
    expect(isForbiddenMcpArg('--env-file=.env')).toBe(true);
    expect(isForbiddenMcpArg('--script-shell')).toBe(true);
    expect(isForbiddenMcpArg('--script-shell=evil.exe')).toBe(true);
    expect(filterSafeMcpArgs(['--env-file', '.env', 'pkg'], 'node')).toEqual(['pkg']);
    expect(filterSafeMcpArgs(['--script-shell', 'cmd.exe', 'exec', 'pkg'], 'npm')).toEqual([
      'exec',
      'pkg',
    ]);
    expect(isForbiddenMcpArg('--userconfig')).toBe(true);
    expect(isForbiddenMcpArg('--globalconfig=.npmrc')).toBe(true);
    expect(filterSafeMcpArgs(['--userconfig', 'evil.npmrc', 'exec', 'pkg'], 'npm')).toEqual([
      'exec',
      'pkg',
    ]);
    expect(isForbiddenMcpArg('--init-module')).toBe(true);
    expect(isForbiddenMcpArg('--init-module=evil.js')).toBe(true);
    expect(filterSafeMcpArgs(['--init-module', 'evil.js', 'server.js'], 'node')).toEqual(['server.js']);
  });

  it('prepareMcpCall allowlist ve boş listeyi reddeder', () => {
    expect(() => prepareMcpCall({ mcpEnabled: false, mcpServers: [] }, { server: 'docs', tool: 'query-docs' })).toThrow(
      /MCP kapalı/,
    );
    expect(() => prepareMcpCall(enabled, { server: 'docs', tool: 'hf_jobs' })).toThrow(/izin listesinde değil/);
    expect(() =>
      prepareMcpCall(
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', command: 'npx', args: ['-y', 'pkg'], allowedTools: [] }],
        },
        { server: 'docs', tool: 'query-docs' },
      ),
    ).toThrow(/izinli araç listesi boş/);
    expect(() =>
      prepareMcpServer(
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', command: 'npx', args: ['-c', 'calc'], allowedTools: ['query-docs'] }],
        },
        { server: 'docs' },
      ),
    ).toThrow(/yorumlayıcı bayrağı/);
    expect(
      prepareMcpServer(
        {
          mcpEnabled: true,
          mcpServers: [{ id: 'docs', command: '  npx  ', args: ['  -y  ', '  pkg  '], allowedTools: ['query-docs'] }],
        },
        { server: 'docs' },
      ),
    ).toMatchObject({ command: 'npx', args: ['-y', 'pkg'] });
  });

  it('ilan kesişimi yoksa çağrıyı keser; araç adı ve argüman tavanı', () => {
    expect(() =>
      prepareMcpCall(enabled, { server: 'docs', tool: 'query-docs' }, { advertised: ['other'], allowed: [] }),
    ).toThrow(/ilan ettiği/);
    const ok = prepareMcpCall(
      enabled,
      { server: 'docs', tool: 'query-docs', arguments: { q: 'zod' } },
      { advertised: ['query-docs'], allowed: ['query-docs'] },
    );
    expect(ok.tool).toBe('query-docs');
    expect(ok.toolArgs).toEqual({ q: 'zod' });
    expect(
      prepareMcpCall(
        enabled,
        { server: 'docs', tool: 'query-docs', arguments: '{"q":"zod"}' },
        { advertised: ['query-docs'], allowed: ['query-docs'] },
      ).toolArgs,
    ).toEqual({ q: 'zod' });
    expect(sanitizeMcpToolArgs('{"q":"zod"}')).toEqual({ q: 'zod' });
    const dirty = Object.assign(Object.create({ leaked: true }), { q: 'zod' });
    const clean = sanitizeMcpToolArgs(dirty);
    expect(clean).toEqual({ q: 'zod' });
    expect(Object.getPrototypeOf(clean)).toBe(Object.prototype);
    expect((clean as { leaked?: boolean }).leaked).toBeUndefined();
    expect(sanitizeMcpToolArgs('nope')).toEqual({});
    expect(() => sanitizeMcpToolName('../etc')).toThrow(/geçersiz/);
    expect(sanitizeMcpToolName('github/search')).toBe('github/search');
    expect(sanitizeMcpToolName(`browser_${'x'.repeat(56)}`)).toBe(`browser_${'x'.repeat(56)}`);
    expect(() => sanitizeMcpToolName(`browser_${'x'.repeat(57)}`)).toThrow(/geçersiz/);
    expect(() => sanitizeMcpToolName('foo/../bar')).toThrow(/geçersiz/);
    const cyclic: Record<string, unknown> = { q: 'zod' };
    cyclic.self = cyclic;
    expect(() => sanitizeMcpToolArgs(cyclic)).toThrow(/geçersiz/);
    expect(() => sanitizeMcpToolArgs({ blob: 'x'.repeat(40_000) })).toThrow(/çok büyük/);
  });

  it('stdout satırları ayırır, tavanı aşınca atar', () => {
    const first = appendMcpStdout('', '{"id":1}\n{"id":2}\npartial');
    expect(first.lines).toEqual(['{"id":1}', '{"id":2}']);
    expect(first.buffer).toBe('partial');
    expect(appendMcpStdout('', '{"id":1}\r{"id":2}\r').lines).toEqual(['{"id":1}', '{"id":2}']);
    expect(appendMcpStdout('', '{"id":1}\r\n{"id":2}\r\n').lines).toEqual(['{"id":1}', '{"id":2}']);
    expect(() => appendMcpStdout('a'.repeat(MCP_STDOUT_BUFFER_CAP), 'z')).toThrow(/çıktı tavanı/);
    const frame = appendMcpStdout('', 'Content-Length: 8\r\n\r\n{"id":1}');
    expect(frame.lines).toEqual(['{"id":1}']);
    expect(frame.buffer).toBe('');
    expect(appendMcpStdout('', 'Content-Length : 8\r\n\r\n{"id":1}').lines).toEqual(['{"id":1}']);
    expect(appendMcpStdout('', 'Content-Length:8\r\n\r\n{"id":1}').lines).toEqual(['{"id":1}']);
    const partial = appendMcpStdout('', 'Content-Length: 8\r\n\r\n{"id":');
    expect(partial.lines).toEqual([]);
    expect(partial.buffer).toContain('Content-Length');
    const unicode = appendMcpStdout('', `Content-Length: ${Buffer.byteLength('{"x":"ğ"}', 'utf8')}\r\n\r\n{"x":"ğ"}`);
    expect(unicode.lines).toEqual(['{"x":"ğ"}']);
    const encoded = encodeMcpStdioFrame({ id: 1, method: 'initialize' });
    expect(encoded.startsWith('Content-Length:')).toBe(true);
    expect(encoded.endsWith('\n')).toBe(true);
    expect(appendMcpStdout('', encoded).lines).toEqual([JSON.stringify({ id: 1, method: 'initialize' })]);
    expect(mcpToolsFromListResult({ tools: [{ name: 'a' }], nextCursor: 'p2' })).toEqual([{ name: 'a' }]);
    expect(mcpToolsFromListResult({ tools: { name: 'solo' } })).toEqual([{ name: 'solo' }]);
    expect(mcpToolsFromListResult([{ name: 'bare' }])).toEqual([{ name: 'bare' }]);
    expect(mcpToolsFromListResult({ Tools: [{ name: 'A' }] })).toEqual([{ name: 'A' }]);
    expect(mcpToolsFromListResult({ Tools: [{ Name: 'Search', Description: 'q' }] })).toEqual([
      { name: 'Search', description: 'q' },
    ]);
    expect(mcpToolsFromListResult([{ Name: 'bare' }])).toEqual([{ name: 'bare' }]);
    expect(mcpToolsFromListResult({ tools: [{ name: '  query-docs  ', description: '  q  ' }] })).toEqual([
      { name: 'query-docs', description: 'q' },
    ]);
    expect(mcpListNextCursor({ next_cursor: 'p2' })).toBe('p2');
    expect(mcpListNextCursor({ NextCursor: 'p3' })).toBe('p3');
    expect(mcpListNextCursor({ cursor: 'p4' })).toBe('p4');
    expect(mcpUniqueToolNames(['a', 'a', 'b'])).toEqual(['a', 'b']);
    expect(mcpListNextCursor({ tools: [], nextCursor: ' p2 ' })).toBe('p2');
    expect(mcpListNextCursor({ tools: [], nextCursor: 3 })).toBe('3');
    expect(mcpListNextCursor({ tools: [] })).toBeUndefined();
    expect(mcpListAdvanceCursor({ nextCursor: 'p2' })).toBe('p2');
    expect(mcpListAdvanceCursor({ nextCursor: 'p2' }, 'p2')).toBeUndefined();
    expect(mcpListCursorParam('3')).toBe(3);
    expect(mcpListCursorParam('0')).toBe(0);
    expect(mcpListCursorParam('p2')).toBe('p2');
    expect(mcpToolsFromListResult(null)).toEqual([]);
  });

  it('sunucu ping ve roots/list cevaplar, RPC hatası mesajsız kod kullanır', () => {
    expect(mcpServerRequestReply({ method: 'ping', id: 9 })).toEqual({
      jsonrpc: '2.0',
      id: 9,
      result: {},
    });
    expect(mcpServerRequestReply({ method: 'roots/list', id: 'r1' })).toEqual({
      jsonrpc: '2.0',
      id: 'r1',
      result: { roots: [] },
    });
    expect(mcpServerRequestReply({ method: 'sampling/createMessage', id: 3 })).toEqual({
      jsonrpc: '2.0',
      id: 3,
      error: { code: -32601, message: 'Method not found' },
    });
    expect(mcpServerRequestReply({ method: 'ping' })).toBeNull();
    expect(mcpServerRequestReply({ id: 1, result: {} })).toBeNull();
    expect(mcpServerRequestReply({ method: 'initialize', id: 1, result: { ok: true } })).toBeNull();
    expect(mcpServerRequestReply({ method: 'resources/list', id: 4 })).toEqual({
      jsonrpc: '2.0',
      id: 4,
      result: { resources: [] },
    });
    expect(mcpServerRequestReply({ method: 'prompts/list', id: 5 })).toEqual({
      jsonrpc: '2.0',
      id: 5,
      result: { prompts: [] },
    });
    expect(mcpServerRequestReply({ method: 'resources/templates/list', id: 6 })).toEqual({
      jsonrpc: '2.0',
      id: 6,
      result: { resourceTemplates: [] },
    });
    expect(mcpServerRequestReply({ method: 'notifications/progress', id: 1 })).toBeNull();
    expect(mcpServerRequestReply({ method: 'Ping', id: 10 })).toEqual({
      jsonrpc: '2.0',
      id: 10,
      result: {},
    });
    expect(mcpServerRequestReply({ method: ' Roots/List ', id: 'r2' })).toEqual({
      jsonrpc: '2.0',
      id: 'r2',
      result: { roots: [] },
    });
    expect(mcpServerRequestReply({ method: 'logging/setLevel', id: 7 })).toEqual({
      jsonrpc: '2.0',
      id: 7,
      result: {},
    });
    expect(mcpServerRequestReply({ method: 'LOGGING/SETLEVEL', id: 11 })).toEqual({
      jsonrpc: '2.0',
      id: 11,
      result: {},
    });
    expect(mcpServerRequestReply({ method: 'Notifications/Progress', id: 1 })).toBeNull();
    expect(mcpServerRequestReply({ method: 'elicitation/create', id: 8 })).toEqual({
      jsonrpc: '2.0',
      id: 8,
      result: { action: 'cancel' },
    });
    expect(mcpRpcErrorMessage({ code: -32602 }, 'MCP initialize başarısız.')).toBe(
      'MCP initialize başarısız. (-32602)',
    );
    expect(mcpRpcErrorMessage({ message: '  bad schema  ' }, 'fallback')).toBe('bad schema');
    expect(mcpRpcErrorMessage(null, 'MCP tools/call başarısız.')).toBe('MCP tools/call başarısız.');
    expect(mcpRpcErrorMessage({ data: '  missing tool  ' }, 'fallback')).toBe('missing tool');
    expect(mcpRpcErrorMessage({ data: { reason: 'unknown tool' } }, 'fallback')).toBe('unknown tool');
    expect(mcpRpcErrorMessage({ data: [{ message: 'q required' }] }, 'fallback')).toBe('q required');
    expect(mcpRpcErrorMessage({ data: { errors: [{ message: 'bad type' }] } }, 'fallback')).toBe(
      'bad type',
    );
    expect(
      mcpRpcErrorMessage({ data: { issues: [{ message: 'Expected string' }] } }, 'fallback'),
    ).toBe('Expected string');
    expect(mcpRpcErrorMessage({ data: { errors: [{ msg: 'field required' }] } }, 'fallback')).toBe(
      'field required',
    );
    expect(mcpRpcErrorMessage({ data: { detail: 'not found' } }, 'fallback')).toBe('not found');
    expect(mcpRpcErrorMessage({ message: { message: 'nested fail' } }, 'fallback')).toBe('nested fail');
    expect(mcpRpcErrorMessage('  string error  ', 'fallback')).toBe('string error');
    expect(mcpParseRpcMessages('[{"id":1,"result":{}},{"id":2,"method":"ping"}]')).toEqual([
      { id: 1, result: {} },
      { id: 2, method: 'ping' },
    ]);
    expect(mcpParseRpcMessages('{"id":1,"result":{}}')).toEqual([{ id: 1, result: {} }]);
    expect(mcpParseRpcMessages('null')).toEqual([]);
    expect(mcpParseRpcMessages('{"id":1,"result":{}}{"id":2,"method":"ping"}')).toEqual([
      { id: 1, result: {} },
      { id: 2, method: 'ping' },
    ]);
    expect(mcpParseConcatenatedJson('{"id":1}{"id":2}')).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it('stderr kuyruğunu tutar, tek parçada tavanı aşmaz', () => {
    const head = 'HEAD-UNIQUE-MARKER';
    const tail = 'TAIL-UNIQUE-MARKER';
    const kept = appendMcpStderr('', `${head}${'x'.repeat(MCP_STDERR_CAP)}${tail}`);
    expect(kept.length).toBe(MCP_STDERR_CAP);
    expect(kept).toContain(tail);
    expect(kept).not.toContain(head);
    const rolled = appendMcpStderr('aaaa', 'b'.repeat(MCP_STDERR_CAP));
    expect(rolled).toBe('b'.repeat(MCP_STDERR_CAP));
    expect(appendMcpStderr('keep', '')).toBe('keep');
    expect(appendMcpStderr('', '\x1B[31merror\x1B[0m')).toBe('error');
    expect(appendMcpStderr('', '\x1B]0;title\x07fail')).toBe('fail');
  });

  it('JSON-RPC id sayı veya sayı-string kabul eder', () => {
    expect(resolveMcpRpcId(1)).toBe(1);
    expect(resolveMcpRpcId('2')).toBe(2);
    expect(resolveMcpRpcId('  3  ')).toBe(3);
    expect(resolveMcpRpcId('1.0')).toBe(1);
    expect(resolveMcpRpcId('01')).toBeUndefined();
    expect(resolveMcpRpcId(0)).toBeUndefined();
    expect(resolveMcpRpcId('nope')).toBeUndefined();
    expect(resolveMcpRpcId(1.5)).toBeUndefined();
  });
});
