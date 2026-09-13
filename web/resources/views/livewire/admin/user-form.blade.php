<div class="max-w-2xl">
    <form wire:submit="save" class="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 space-y-5">

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
                <label class="field-label">Full name</label>
                <input type="text" wire:model="name" class="field-input @error('name') field-error @enderror">
                @error('name') <p class="field-err-msg">{{ $message }}</p> @enderror
            </div>
            <div>
                <label class="field-label">Username</label>
                <input type="text" wire:model="username" class="field-input @error('username') field-error @enderror">
                @error('username') <p class="field-err-msg">{{ $message }}</p> @enderror
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
                <label class="field-label">Email address</label>
                <input type="email" wire:model="email" class="field-input @error('email') field-error @enderror">
                @error('email') <p class="field-err-msg">{{ $message }}</p> @enderror
            </div>
            <div>
                <label class="field-label">Mobile</label>
                <input type="text" wire:model="mobile" maxlength="10" class="field-input @error('mobile') field-error @enderror">
                @error('mobile') <p class="field-err-msg">{{ $message }}</p> @enderror
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
                <label class="field-label">Role</label>
                <select wire:model="role" class="field-input @error('role') field-error @enderror">
                    @foreach(\App\Models\User::ROLES as $roleOption)
                    <option value="{{ $roleOption }}">{{ $roleOption }}</option>
                    @endforeach
                </select>
            </div>
            <div>
                <label class="field-label">Designation</label>
                <select wire:model.live="designationId" class="field-input">
                    <option value="">—</option>
                    @foreach($designations as $designation)
                    <option value="{{ $designation->id }}">{{ $designation->name }}</option>
                    @endforeach
                </select>
                <p class="field-hint">Sets a starting privilege preset — it doesn't stay linked afterward.</p>
            </div>
        </div>

        <div>
            <label class="field-label">Post (specific posting, free text)</label>
            <input type="text" wire:model="post" placeholder="e.g. Deputy Excise Commissioner (Prevention & Enforcement)" class="field-input @error('post') field-error @enderror">
            @error('post') <p class="field-err-msg">{{ $message }}</p> @enderror
        </div>

        <div>
            <label class="field-label">Privileges</label>
            <div class="grid grid-cols-2 gap-2 mt-1">
                @foreach(\App\Models\User::PRIVILEGES as $privilege)
                <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 cursor-pointer select-none">
                    <input type="checkbox" wire:model="privileges" value="{{ $privilege }}"
                           class="rounded border-slate-300 dark:border-slate-600 text-govviolet-600 focus:ring-govviolet-500">
                    {{ $privilege }}
                </label>
                @endforeach
            </div>
            <p class="field-hint">Ignored for the Admin role — an Admin has every privilege implicitly.</p>
        </div>

        <div class="flex items-center gap-3 pt-2">
            <button type="submit" class="bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-5 rounded-lg transition-colors">
                {{ $user ? 'Save changes' : 'Create account' }}
            </button>
            <a href="{{ route('admin.users.index') }}" wire:navigate class="text-sm text-slate-500 hover:underline">Cancel</a>
        </div>
    </form>
</div>
