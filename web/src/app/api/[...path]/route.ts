
import { NextRequest, NextResponse } from 'next/server';

// Disable body parsing to handle large file uploads
export const dynamic = 'force-dynamic';
export const maxDuration = 300; // 5 minutes adjustment

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
    const path = (await params).path.join('/');
    const url = `http://127.0.0.1:5001/api/${path}${req.nextUrl.search}`;

    console.log(`[Proxy] ${req.method} ${url}`);

    try {
        const headers = new Headers(req.headers);
        headers.delete('host');
        headers.delete('connection');
        headers.delete('accept-encoding');

        // Forward the request to Flask
        const res = await fetch(url, {
            method: req.method,
            headers: headers,
            body: req.method !== 'GET' && req.method !== 'HEAD' ? req.body : undefined,
            // @ts-expect-error RequestInit in Node fetch supports duplex for stream bodies.
            duplex: 'half',
        });

        const resHeaders = new Headers(res.headers);
        if ((resHeaders.get('content-type') || '').includes('text/event-stream')) {
            resHeaders.set('Cache-Control', 'no-cache, no-transform');
            resHeaders.set('X-Accel-Buffering', 'no');
            resHeaders.delete('content-length');
            resHeaders.delete('Content-Length');
            resHeaders.delete('content-encoding');
            resHeaders.delete('Content-Encoding');
        }

        // Stream the response back
        return new NextResponse(res.body, {
            status: res.status,
            statusText: res.statusText,
            headers: resHeaders,
        });

    } catch (error) {
        console.error('[Proxy Error]', error);
        return NextResponse.json(
            { error: 'Internal Server Error', details: String(error) },
            { status: 500 }
        );
    }
}

export { handler as GET, handler as POST, handler as PUT, handler as DELETE, handler as PATCH, handler as HEAD };
