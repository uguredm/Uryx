-- Jarvis — PostgreSQL başlangıç kurulumu
-- Bu dosya yalnızca veritabanı ilk kez oluşturulurken çalışır.

-- Trigram indexleri: dosya adı / hafıza içeriği üzerinde bulanık arama
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- UUID üretimi
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Aksan/büyük-küçük duyarsız karşılaştırma (Türkçe arama kalitesi için)
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Türkçe full-text search konfigürasyonu.
-- PostgreSQL'de yerleşik 'turkish' snowball stemmer mevcuttur; unaccent ile
-- birleştirerek 'jarvis_turkish' konfigürasyonunu tanımlıyoruz.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'jarvis_turkish') THEN
        CREATE TEXT SEARCH CONFIGURATION jarvis_turkish (COPY = simple);
        ALTER TEXT SEARCH CONFIGURATION jarvis_turkish
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, simple;
    END IF;
END
$$;
