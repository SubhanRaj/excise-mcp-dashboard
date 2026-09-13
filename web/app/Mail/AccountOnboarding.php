<?php

namespace App\Mail;

use App\Models\User;
use Illuminate\Bus\Queueable;
use Illuminate\Mail\Mailable;
use Illuminate\Queue\SerializesModels;

class AccountOnboarding extends Mailable
{
    use Queueable, SerializesModels;

    public function __construct(public User $user, public string $url) {}

    public function build(): self
    {
        return $this->subject('Activate your account')
            ->view('emails.onboarding')
            ->with(['user' => $this->user, 'url' => $this->url]);
    }
}
