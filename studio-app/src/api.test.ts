import { afterEach, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';

afterEach(()=>vi.unstubAllGlobals());

it('forwards the status-check abort signal and treats an interrupted body as offline',async()=>{
  const controller=new AbortController();
  const fetchMock=vi.fn().mockResolvedValue({ok:true,text:()=>Promise.reject(Error('connection lost'))});
  vi.stubGlobal('fetch',fetchMock);
  await expect(api.jarvisRun('board','run',controller.signal)).rejects.toMatchObject({status:0,code:'offline'} satisfies Partial<ApiError>);
  expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
});
