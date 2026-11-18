-- SOUND profil, arkadaşlık ve mesajlaşma şeması (Supabase).
-- Supabase panelinde: SQL Editor → New query → bu dosyanın tamamını yapıştır → Run.
-- Birden fazla kez çalıştırmak güvenlidir, mevcut kitaplık tablolarına dokunmaz.

-- ---------- profiller ----------
-- Giriş yapmış herkes profilleri görebilir; e-posta burada tutulmaz.
-- showcase: profilde gösterilen özet {"top_artists": [...], "albums": [{"name", "count"}], "favorites": 12}
create table if not exists public.profiles (
    id           uuid        primary key references auth.users (id) on delete cascade,
    username     text        not null,
    display_name text        not null default '',
    bio          text        not null default '',
    showcase     jsonb       not null default '{}'::jsonb,
    updated_at   timestamptz not null default now(),
    constraint profiles_username_format check (username ~ '^[a-z0-9_]{3,20}$'),
    constraint profiles_display_name_size check (char_length(display_name) <= 40),
    constraint profiles_bio_size check (char_length(bio) <= 300),
    constraint profiles_showcase_size check (octet_length(showcase::text) <= 8192)
);

create unique index if not exists profiles_username_key on public.profiles (username);

alter table public.profiles enable row level security;

drop policy if exists "profiller herkese acik" on public.profiles;
create policy "profiller herkese acik" on public.profiles
    for select to authenticated using (true);

drop policy if exists "kendi profilini ekler" on public.profiles;
create policy "kendi profilini ekler" on public.profiles
    for insert to authenticated with check (id = auth.uid());

drop policy if exists "kendi profilini degistirir" on public.profiles;
create policy "kendi profilini degistirir" on public.profiles
    for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant insert (id, username, display_name, bio, showcase) on public.profiles to authenticated;
grant update (username, display_name, bio, showcase, updated_at) on public.profiles to authenticated;

-- ---------- arkadaşlıklar ----------
-- İstek gönderen requester, alan addressee. Reddetme ve arkadaşlıktan çıkarma satırı siler.
create table if not exists public.friendships (
    requester  uuid        not null references public.profiles (id) on delete cascade,
    addressee  uuid        not null references public.profiles (id) on delete cascade,
    status     text        not null default 'pending',
    created_at timestamptz not null default now(),
    primary key (requester, addressee),
    constraint friendships_status check (status in ('pending', 'accepted')),
    constraint friendships_not_self check (requester <> addressee)
);

-- İki kişi arasında yönü ne olursa olsun tek kayıt olur
create unique index if not exists friendships_pair
    on public.friendships (least(requester, addressee), greatest(requester, addressee));
create index if not exists friendships_addressee on public.friendships (addressee);

alter table public.friendships enable row level security;

drop policy if exists "kendi arkadasliklarini gorur" on public.friendships;
create policy "kendi arkadasliklarini gorur" on public.friendships
    for select to authenticated using (auth.uid() in (requester, addressee));

drop policy if exists "istek gonderir" on public.friendships;
create policy "istek gonderir" on public.friendships
    for insert to authenticated with check (requester = auth.uid() and status = 'pending');

drop policy if exists "gelen istegi kabul eder" on public.friendships;
create policy "gelen istegi kabul eder" on public.friendships
    for update to authenticated using (addressee = auth.uid()) with check (addressee = auth.uid() and status = 'accepted');

drop policy if exists "arkadasliktan cikar" on public.friendships;
create policy "arkadasliktan cikar" on public.friendships
    for delete to authenticated using (auth.uid() in (requester, addressee));

revoke all on public.friendships from anon, authenticated;
grant select, delete on public.friendships to authenticated;
grant insert (requester, addressee) on public.friendships to authenticated;
grant update (status) on public.friendships to authenticated;

-- ---------- mesajlar ----------
-- Yalnızca arkadaşlar birbirine yazabilir. Gönderen ve zaman sunucuda belirlenir.
create table if not exists public.messages (
    id         bigint      generated always as identity primary key,
    sender     uuid        not null default auth.uid() references public.profiles (id) on delete cascade,
    recipient  uuid        not null references public.profiles (id) on delete cascade,
    body       text        not null,
    created_at timestamptz not null default now(),
    read_at    timestamptz,
    constraint messages_body_size check (char_length(btrim(body)) between 1 and 2000),
    constraint messages_not_self check (sender <> recipient)
);

create index if not exists messages_sent on public.messages (sender, recipient, id desc);
create index if not exists messages_received on public.messages (recipient, sender, id desc);
create index if not exists messages_unread on public.messages (recipient) where read_at is null;

alter table public.messages enable row level security;

drop policy if exists "kendi mesajlarini gorur" on public.messages;
create policy "kendi mesajlarini gorur" on public.messages
    for select to authenticated using (auth.uid() in (sender, recipient));

drop policy if exists "arkadasina yazar" on public.messages;
create policy "arkadasina yazar" on public.messages
    for insert to authenticated with check (
        sender = auth.uid() and exists (
            select 1 from public.friendships f
            where f.status = 'accepted'
              and ((f.requester = auth.uid() and f.addressee = recipient)
                or (f.addressee = auth.uid() and f.requester = recipient))
        )
    );

drop policy if exists "okundu isaretler" on public.messages;
create policy "okundu isaretler" on public.messages
    for update to authenticated using (recipient = auth.uid()) with check (recipient = auth.uid());

revoke all on public.messages from anon, authenticated;
grant select on public.messages to authenticated;
grant insert (recipient, body) on public.messages to authenticated;
grant update (read_at) on public.messages to authenticated;

-- ---------- kötüye kullanım sınırları ----------
create or replace function public.messages_limit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if (select count(*) from public.messages
        where sender = new.sender and created_at > now() - interval '1 minute') >= 30 then
        raise exception 'Çok hızlı mesaj gönderiyorsun; biraz bekle.' using errcode = 'P0001';
    end if;
    return new;
end $$;

drop trigger if exists messages_limit on public.messages;
create trigger messages_limit before insert on public.messages
    for each row execute function public.messages_limit();

create or replace function public.friendships_limit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if (select count(*) from public.friendships
        where requester = new.requester and created_at > now() - interval '1 hour') >= 30 then
        raise exception 'Çok fazla arkadaşlık isteği gönderdin; biraz bekle.' using errcode = 'P0001';
    end if;
    return new;
end $$;

drop trigger if exists friendships_limit on public.friendships;
create trigger friendships_limit before insert on public.friendships
    for each row execute function public.friendships_limit();

-- ---------- anlık bildirim ----------
-- Silinen satırların bilgisi Realtime'da satır güvenliğine tabi olmadığı için arkadaşlık tablosu yayınlanmaz.
-- Arkadaşlık değişince iki tarafın kendi "dürtme" satırı güncellenir, uygulama listeyi yeniden okur.
create table if not exists public.social_pings (
    user_id uuid        primary key,
    at      timestamptz not null default now()
);

alter table public.social_pings enable row level security;

drop policy if exists "kendi durtmesini gorur" on public.social_pings;
create policy "kendi durtmesini gorur" on public.social_pings
    for select to authenticated using (user_id = auth.uid());

revoke all on public.social_pings from anon, authenticated;
grant select on public.social_pings to authenticated;

create or replace function public.friendships_ping() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    row_data public.friendships;
begin
    if tg_op = 'DELETE' then
        row_data := old;
    else
        row_data := new;
    end if;
    insert into public.social_pings (user_id, at)
    values (row_data.requester, clock_timestamp()), (row_data.addressee, clock_timestamp())
    on conflict (user_id) do update set at = excluded.at;
    return null;
end $$;

drop trigger if exists friendships_ping on public.friendships;
create trigger friendships_ping after insert or update or delete on public.friendships
    for each row execute function public.friendships_ping();

revoke all on function public.messages_limit() from public, anon, authenticated;
revoke all on function public.friendships_limit() from public, anon, authenticated;
revoke all on function public.friendships_ping() from public, anon, authenticated;

do $$ begin
    alter publication supabase_realtime add table public.messages;
exception when duplicate_object then null;
end $$;

do $$ begin
    alter publication supabase_realtime add table public.social_pings;
exception when duplicate_object then null;
end $$;
