@extends('emails.layout')

@section('title', 'Reset your password')

@section('content')
<p style="margin:0 0 8px;font-size:15px;color:#475569;">Hello {{ $user->name }},</p>
<p style="margin:0 0 28px;font-size:15px;color:#475569;line-height:1.6;">
    We received a request to reset your {{ config('app.name') }} password. Click the button
    below to choose a new one. This link expires in <strong>60 minutes</strong> and can only be
    used once.
</p>
<table cellpadding="0" cellspacing="0" style="margin:0 0 28px;">
    <tr>
        <td style="background:#4a2bc2;border-radius:6px;">
            <a href="{{ $url }}" style="display:inline-block;padding:12px 28px;font-size:15px;font-weight:600;color:#fff;text-decoration:none;border-radius:6px;">
                Reset Password
            </a>
        </td>
    </tr>
</table>
<p style="margin:0 0 4px;font-size:13px;color:#94a3b8;">Or copy this link into your browser:</p>
<p style="margin:0 0 28px;font-size:12px;color:#64748b;word-break:break-all;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 12px;">{{ $url }}</p>
<p style="margin:0;font-size:13px;color:#94a3b8;line-height:1.6;">If you did not request this, you can safely ignore this email — your password stays unchanged.</p>
@endsection
