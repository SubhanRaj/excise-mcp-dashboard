@extends('emails.layout')

@section('title', 'Your sign-in code')

@section('content')
<p style="margin:0 0 8px;font-size:15px;color:#475569;">Hello {{ $user->name }},</p>
<p style="margin:0 0 24px;font-size:15px;color:#475569;line-height:1.6;">
    Use the code below to finish signing in to {{ config('app.name') }}. It's valid for
    <strong>{{ $ttlMinutes }} minutes</strong>.
</p>
<table cellpadding="0" cellspacing="0" style="margin:0 0 8px;width:100%;">
    <tr>
        <td align="center" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;">
            <span style="font-size:36px;font-weight:700;letter-spacing:0.3em;color:#4a2bc2;">{{ $code }}</span>
        </td>
    </tr>
</table>
<p style="margin:0 0 24px;font-size:12px;color:#94a3b8;text-align:center;">Tap and hold the code to copy it.</p>
<p style="margin:0;font-size:13px;color:#94a3b8;line-height:1.6;">If you did not attempt to sign in, you can safely ignore this email — your account is still secure.</p>
@endsection
