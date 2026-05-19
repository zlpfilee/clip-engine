# 🎬 ClipEngine - İçerik Otomasyon Merkezi

ClipEngine, sosyal medya için otomatik video kesme, kırpma (dikey formata çevirme), altyazı ve filigran ekleme işlemlerini yapan yapay zeka destekli bir otomasyon sistemidir.

---

## 🚀 Arkadaşlar İçin Kurulum (Tek Tıkla Uygulama!)

Arkadaşlarının Python, FFmpeg, Git kurmasına veya herhangi bir "Token" girmesine kesinlikle gerek yoktur. Onlara sadece **`ClipEngine.exe`** dosyasını göndermeniz yeterlidir.

### Kurulum Adımları:
1. Sana gönderilen **`ClipEngine.exe`** dosyasını bilgisayarında boş bir klasöre koy (Örn: Masaüstünde `ClipEngine` adında bir klasör oluşturup içine atabilirsin).
2. **`ClipEngine.exe`**'ye çift tıkla.
3. Program arka planda gerekli tüm altyapıyı (Python, FFmpeg ve kodları) internetten **otomatik** kuracaktır.
4. Kurulum bittiğinde tarayıcında kontrol paneli açılacaktır. 🎉

> [!NOTE]
> Windows ilk açılışta "Kişisel bilgisayarınızı korudu" uyarısı verirse: **"Daha fazla bilgi"** -> **"Yine de çalıştır"** demeleri yeterlidir.
> **Her açılışta güncellemeleri otomatik kontrol eder ve kurar!** Sen kodda güncelleme yapıp push attığında onlarda da otomatik güncellenir.

---

## 🛠 Geliştirici Bilgileri & Güncelleme Yayınlama (Senin İçin)

### ⚠️ ÇOK ÖNEMLİ: REPO'YU PUBLIC YAPMALISIN!
Arkadaşlarının hiçbir şifre veya token girmeden otomatik güncelleme alabilmesi için, GitHub üzerindeki `clip-engine` deponun **PUBLIC (Herkese Açık)** olması zorunludur.
* GitHub'da deponun **Settings** -> **General** sayfasına git.
* En alttaki **Danger Zone** kısmından **Change repository visibility** diyerek repoyu **Public** yap.
* *(Eğer kodların çalınmasından veya başkasının görmesinden endişe etmiyorsan en kolay yol budur).*

### 1. Kodları Güncelleme ve Yayınlama
Kodlarda bir değişiklik yaptığında arkadaşlarının da bu güncellemeyi alması için şu adımları takip et:

1. **`version.txt`** dosyasındaki sürüm numarasını arttır (Örn: `1.0.0` ise `1.0.1` yap).
2. Kodlarını normal şekilde Git ile push'la:
   ```bash
   git add -A
   git commit -m "v1.0.1: [Yapılan değişiklikler]"
   git push
   ```
3. Arkadaşlar uygulamayı sonraki açışlarında bu değişikliği otomatik çekecektir.

### 2. Exe Dosyasını Yeniden Derleme (Gerekirse)
Eğer launcher arayüzünde veya kurulum kodlarında (`launcher.py` veya `ClipEngine.spec`) bir değişiklik yaparsan exe'yi şu komutla yeniden derleyebilirsin:
```bash
pyinstaller ClipEngine.spec --clean
```
Yeni oluşan `dist/ClipEngine.exe` dosyasını arkadaşlarına tekrar dağıtman gerekir. (Sadece launcher kodunu değiştirirsen exe'yi güncellemen gerekir. FastAPI/Frontend kodlarını güncellediğinde exe'yi güncellemene gerek yoktur, git push yeterlidir).
