-- SOUND grupları ve "Birlikte dinle" davetleri (Supabase).
-- social.sql'den SONRA çalıştırılır: SQL Editor → New query → bu dosyanın tamamını yapıştır → Run.
-- Birden fazla kez çalıştırmak güvenlidir.

-- ---------- birebir mesajlarda ortak dinleme daveti ----------
-- kind = 'jam' olan mesajın gövdesi oda kodudur; uygulama onu "arama" gibi gösterir.
alter table public.messages add column if not exists kind text not null default 'text';
do $$ begin
    alter table public.messages add constraint messages_kind check (kind in ('text', 'jam'));
exception when duplicate_object then null;
end $$;
grant insert (recipient, body, kind) on public.messages to authenticated;

-- ---------- gruplar ----------
create table if not exists public.groups (
    id         uuid        primary key default gen_random_uuid(),
    name       text        not null,
    created_by uuid        references public.profiles (id) on delete set null,
    created_at timestamptz not null default now(),
    constraint groups_name_size check (char_length(btrim(name)) between 1 and 40)
);

create table if not exists public.group_members (
    group_id  uuid        not null references public.groups (id) on delete cascade,
    user_id   uuid        not null references public.profiles (id) on delete cascade,
    role      text        not null default 'member',
    last_read bigint      not null default 0,
    joined_at timestamptz not null default now(),
    primary key (group_id, user_id),
    constraint group_members_role check (role in ('admin', 'member'))
);
create index if not exists group_members_user on public.group_members (user_id);

-- kind: text (yazı), jam (ortak dinleme daveti, gövde oda kodu), system (gruba katıldı / ayrıldı gibi)
create table if not exists public.group_messages (
    id         bigint      generated always as identity primary key,
    group_id   uuid        not null references public.groups (id) on delete cascade,
    sender     uuid        default auth.uid() references public.profiles (id) on delete set null,
    body       text        not null,
    kind       text        not null default 'text',
    created_at timestamptz not null default now(),
    constraint group_messages_kind check (kind in ('text', 'jam', 'system')),
    constraint group_messages_body_size check (char_length(btrim(body)) between 1 and 2000)
);
create index if not exists group_messages_group on public.group_messages (group_id, id desc);

create or replace function public.is_group_member(g uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.group_members where group_id = g and user_id = auth.uid())
$$;

create or replace function public.is_group_admin(g uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.group_members where group_id = g and user_id = auth.uid() and role = 'admin')
$$;

create or replace function public.are_friends(a uuid, b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.friendships
                   where status = 'accepted' and least(requester, addressee) = least(a, b)
                     and greatest(requester, addressee) = greatest(a, b))
$$;

alter table public.groups enable row level security;
alter table public.group_members enable row level security;
alter table public.group_messages enable row level security;

drop policy if exists "uyesi oldugu grubu gorur" on public.groups;
create policy "uyesi oldugu grubu gorur" on public.groups
    for select to authenticated using (public.is_group_member(id));

drop policy if exists "grubun uyelerini gorur" on public.group_members;
create policy "grubun uyelerini gorur" on public.group_members
    for select to authenticated using (public.is_group_member(group_id));

drop policy if exists "grubun mesajlarini gorur" on public.group_messages;
create policy "grubun mesajlarini gorur" on public.group_messages
    for select to authenticated using (public.is_group_member(group_id));

drop policy if exists "gruba yazar" on public.group_messages;
create policy "gruba yazar" on public.group_messages
    for insert to authenticated with check (sender = auth.uid() and kind in ('text', 'jam') and public.is_group_member(group_id));

-- Yazma işlemleri (grup kurma, üye ekleme/çıkarma, yönetici, ad) aşağıdaki işlevlerle yapılır.
revoke all on public.groups, public.group_members, public.group_messages from anon, authenticated;
grant select on public.groups, public.group_members, public.group_messages to authenticated;
grant insert (group_id, body, kind) on public.group_messages to authenticated;

-- ---------- grup işlemleri ----------
create or replace function public._group_note(g uuid, note text) returns void
language sql security definer set search_path = '' as $$
    insert into public.group_messages (group_id, sender, body, kind) values (g, auth.uid(), left(note, 2000), 'system')
$$;

create or replace function public._group_name_of(u uuid) returns text
language sql stable security definer set search_path = '' as $$
    select coalesce(nullif(display_name, ''), username) from public.profiles where id = u
$$;

create or replace function public.create_group(p_name text, p_members uuid[]) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
    me uuid := auth.uid();
    g uuid;
    m uuid;
begin
    if me is null or not exists (select 1 from public.profiles where id = me) then
        raise exception 'Önce profilini oluştur.' using errcode = 'P0001';
    end if;
    if char_length(btrim(coalesce(p_name, ''))) not between 1 and 40 then
        raise exception 'Grup adı 1-40 karakter olmalı.' using errcode = 'P0001';
    end if;
    if coalesce(array_length(p_members, 1), 0) > 49 then
        raise exception 'Bir grupta en fazla 50 kişi olabilir.' using errcode = 'P0001';
    end if;
    if (select count(*) from public.groups where created_by = me and created_at > now() - interval '1 hour') >= 10 then
        raise exception 'Çok fazla grup kurdun; biraz bekle.' using errcode = 'P0001';
    end if;
    insert into public.groups (name, created_by) values (btrim(p_name), me) returning id into g;
    insert into public.group_members (group_id, user_id, role) values (g, me, 'admin');
    foreach m in array coalesce(p_members, '{}') loop
        if m <> me and public.are_friends(me, m) then
            insert into public.group_members (group_id, user_id) values (g, m) on conflict do nothing;
        end if;
    end loop;
    perform public._group_note(g, public._group_name_of(me) || ' grubu kurdu');
    return g;
end $$;

create or replace function public.add_group_members(g uuid, p_members uuid[]) returns void
language plpgsql security definer set search_path = '' as $$
declare
    me uuid := auth.uid();
    m uuid;
begin
    if not public.is_group_admin(g) then
        raise exception 'Üye eklemeyi yalnızca yöneticiler yapabilir.' using errcode = 'P0001';
    end if;
    foreach m in array coalesce(p_members, '{}') loop
        if (select count(*) from public.group_members where group_id = g) >= 50 then
            raise exception 'Bir grupta en fazla 50 kişi olabilir.' using errcode = 'P0001';
        end if;
        if public.are_friends(me, m) and not exists (select 1 from public.group_members where group_id = g and user_id = m) then
            insert into public.group_members (group_id, user_id) values (g, m);
            perform public._group_note(g, public._group_name_of(me) || ', ' || public._group_name_of(m) || ' kişisini ekledi');
        end if;
    end loop;
end $$;

create or replace function public.remove_group_member(g uuid, u uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if u = auth.uid() then
        raise exception 'Kendini çıkarmak için gruptan ayrıl.' using errcode = 'P0001';
    end if;
    if not public.is_group_admin(g) then
        raise exception 'Üye çıkarmayı yalnızca yöneticiler yapabilir.' using errcode = 'P0001';
    end if;
    delete from public.group_members where group_id = g and user_id = u;
    if found then
        perform public._group_note(g, public._group_name_of(auth.uid()) || ', ' || public._group_name_of(u) || ' kişisini çıkardı');
    end if;
end $$;

create or replace function public.leave_group(g uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare
    me uuid := auth.uid();
begin
    delete from public.group_members where group_id = g and user_id = me;
    if not found then
        return;
    end if;
    if not exists (select 1 from public.group_members where group_id = g) then
        delete from public.groups where id = g;  -- son kişi de çıktı
        return;
    end if;
    if not exists (select 1 from public.group_members where group_id = g and role = 'admin') then
        update public.group_members set role = 'admin'  -- yönetici kalmadı: en eski üye yönetici olur
        where group_id = g and user_id = (select user_id from public.group_members where group_id = g order by joined_at, user_id limit 1);
    end if;
    insert into public.group_messages (group_id, sender, body, kind) values (g, me, public._group_name_of(me) || ' gruptan ayrıldı', 'system');
end $$;

create or replace function public.set_group_admin(g uuid, u uuid, on_off boolean) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if not public.is_group_admin(g) then
        raise exception 'Bunu yalnızca yöneticiler yapabilir.' using errcode = 'P0001';
    end if;
    if not on_off and (select count(*) from public.group_members where group_id = g and role = 'admin' and user_id <> u) = 0 then
        raise exception 'Grupta en az bir yönetici kalmalı.' using errcode = 'P0001';
    end if;
    update public.group_members set role = case when on_off then 'admin' else 'member' end where group_id = g and user_id = u;
end $$;

create or replace function public.rename_group(g uuid, p_name text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if not public.is_group_admin(g) then
        raise exception 'Grup adını yalnızca yöneticiler değiştirebilir.' using errcode = 'P0001';
    end if;
    if char_length(btrim(coalesce(p_name, ''))) not between 1 and 40 then
        raise exception 'Grup adı 1-40 karakter olmalı.' using errcode = 'P0001';
    end if;
    update public.groups set name = btrim(p_name) where id = g;
    perform public._group_note(g, public._group_name_of(auth.uid()) || ' grubun adını “' || btrim(p_name) || '” yaptı');
end $$;

create or replace function public.mark_group_read(g uuid) returns void
language sql security definer set search_path = '' as $$
    update public.group_members
    set last_read = greatest(last_read, coalesce((select max(id) from public.group_messages where group_id = g), 0))
    where group_id = g and user_id = auth.uid()
$$;

-- Kenar listesi: gruplarım, son mesaj ve okunmamış sayısı
create or replace function public.my_groups()
returns table (id uuid, name text, role text, members integer, last_body text, last_kind text, last_sender uuid, last_at timestamptz, unread integer)
language sql stable security definer set search_path = '' as $$
    select g.id, g.name, gm.role,
           (select count(*)::int from public.group_members x where x.group_id = g.id),
           lm.body, lm.kind, lm.sender, coalesce(lm.created_at, g.created_at),
           (select count(*)::int from public.group_messages y
             where y.group_id = g.id and y.id > gm.last_read and y.sender is distinct from auth.uid() and y.kind <> 'system')
    from public.group_members gm
    join public.groups g on g.id = gm.group_id
    left join lateral (select body, kind, sender, created_at from public.group_messages z
                       where z.group_id = g.id order by z.id desc limit 1) lm on true
    where gm.user_id = auth.uid()
    order by coalesce(lm.created_at, g.created_at) desc
$$;

-- ---------- kötüye kullanım sınırı ----------
create or replace function public.group_messages_limit() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.kind <> 'system' and (select count(*) from public.group_messages
        where sender = new.sender and kind <> 'system' and created_at > now() - interval '1 minute') >= 30 then
        raise exception 'Çok hızlı mesaj gönderiyorsun; biraz bekle.' using errcode = 'P0001';
    end if;
    return new;
end $$;

drop trigger if exists group_messages_limit on public.group_messages;
create trigger group_messages_limit before insert on public.group_messages
    for each row execute function public.group_messages_limit();

-- ---------- anlık bildirim ----------
-- Üyelik değişince (eklendi, çıkarıldı, yönetici oldu) gruptaki herkesin ve etkilenen kişinin dürtme satırı güncellenir.
create or replace function public.group_members_ping() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    g uuid := coalesce(new.group_id, old.group_id);
begin
    -- önce kişiler tekilleştirilir, saat sonra eklenir (clock_timestamp her satırda farklı olduğundan
    -- union kopyayı ayıklamıyordu → "ON CONFLICT DO UPDATE command cannot affect row a second time")
    insert into public.social_pings (user_id, at)
    select u, clock_timestamp() from (
        select user_id as u from public.group_members where group_id = g
        union select coalesce(new.user_id, old.user_id)
    ) people
    on conflict (user_id) do update set at = excluded.at;
    return null;
end $$;

drop trigger if exists group_members_ping on public.group_members;
create trigger group_members_ping after insert or update or delete on public.group_members
    for each row execute function public.group_members_ping();

-- Hesap silinince üyelik satırı kendiliğinden düşer: boş kalan grup silinir, yöneticisiz kalan grupta en eski üye yönetici olur.
create or replace function public.group_members_tidy() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if not exists (select 1 from public.group_members where group_id = old.group_id) then
        delete from public.groups where id = old.group_id;
    elsif not exists (select 1 from public.group_members where group_id = old.group_id and role = 'admin') then
        update public.group_members set role = 'admin'
        where group_id = old.group_id
          and user_id = (select user_id from public.group_members where group_id = old.group_id order by joined_at, user_id limit 1);
    end if;
    return null;
end $$;

drop trigger if exists group_members_tidy on public.group_members;
create trigger group_members_tidy after delete on public.group_members
    for each row execute function public.group_members_tidy();

revoke all on function public.group_members_tidy() from public, anon, authenticated;

revoke all on function public.is_group_member(uuid), public.is_group_admin(uuid), public.are_friends(uuid, uuid),
    public._group_note(uuid, text), public._group_name_of(uuid), public.group_messages_limit(), public.group_members_ping()
    from public, anon;
grant execute on function public.is_group_member(uuid), public.is_group_admin(uuid) to authenticated;
revoke all on function public._group_note(uuid, text), public._group_name_of(uuid), public.are_friends(uuid, uuid),
    public.group_messages_limit(), public.group_members_ping() from authenticated;

revoke all on function public.create_group(text, uuid[]), public.add_group_members(uuid, uuid[]), public.remove_group_member(uuid, uuid),
    public.leave_group(uuid), public.set_group_admin(uuid, uuid, boolean), public.rename_group(uuid, text),
    public.mark_group_read(uuid), public.my_groups() from public, anon;
grant execute on function public.create_group(text, uuid[]), public.add_group_members(uuid, uuid[]), public.remove_group_member(uuid, uuid),
    public.leave_group(uuid), public.set_group_admin(uuid, uuid, boolean), public.rename_group(uuid, text),
    public.mark_group_read(uuid), public.my_groups() to authenticated;

do $$ begin
    alter publication supabase_realtime add table public.group_messages;
exception when duplicate_object then null;
end $$;
