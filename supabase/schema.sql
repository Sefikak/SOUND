-- SOUND hesap ve kitaplık eşitleme şeması (Supabase).
-- Supabase panelinde: SQL Editor → New query → bu dosyanın tamamını yapıştır → Run.
-- Birden fazla kez çalıştırmak güvenlidir.

-- Kitaplık öğeleri: her satır bir kullanıcının bir öğesi.
--   fav:<şarkı kimliği>   favori şarkı          {"track": {...}, "at": 1731600000.0}
--   order:favorites       favorilerin sırası    {"ids": [...]}
--   album:<kimlik>        albüm (şarkılarıyla)  {"name", "folder", "created", "source", "tracks": [...], "meta": {id: {...}}}
--   folder:<kimlik>       klasör                {"name", "created"}
-- Silinen öğe satırı kalır, deleted = true olur: silme diğer cihazlara da ulaşsın diye.
create table if not exists public.library_items (
    user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
    key        text        not null check (char_length(key) <= 200),
    value      jsonb,
    deleted    boolean     not null default false,
    device     text,
    updated_at timestamptz not null default now(),
    primary key (user_id, key)
);

create index if not exists library_items_changes on public.library_items (user_id, updated_at);

-- Zaman damgasını her zaman sunucu koyar: cihaz saatleri farklı olsa da "son yazan kazanır" doğru çalışsın.
create or replace function public.library_items_touch() returns trigger
language plpgsql as $$
begin
    new.updated_at := clock_timestamp();
    return new;
end $$;

drop trigger if exists library_items_touch on public.library_items;
create trigger library_items_touch before insert or update on public.library_items
    for each row execute function public.library_items_touch();

-- Herkes yalnızca kendi satırlarını görür ve değiştirir. Uygulamadaki anahtar herkese açık olduğu için şart.
alter table public.library_items enable row level security;

drop policy if exists "kendi satirlari" on public.library_items;
create policy "kendi satirlari" on public.library_items
    for all to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- Proje "yeni tabloları otomatik aç" kapalı kurulduysa tabloya erişim elle verilmeli; açıksa zararı yok.
-- Girişsiz (anon) erişim yok: kitaplık yalnızca giriş yapmış kullanıcıya açık.
revoke all on public.library_items from anon;
grant select, insert, update, delete on public.library_items to authenticated;

-- Ayarlar > Hesap > "Hesabımı sil": kullanıcı ve (cascade ile) bütün kitaplık satırları silinir.
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then
        raise exception 'giris yapilmamis';
    end if;
    delete from auth.users where id = auth.uid();
end $$;

revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;
