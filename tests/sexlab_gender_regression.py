from pathlib import Path
import argparse
import os
import subprocess
import tempfile

parser = argparse.ArgumentParser(description="Compile and run the extracted SexLab policy, menu and serialization code with engine API stand-ins.")
parser.add_argument("--simpleini", required=True, type=Path, help="Directory containing SimpleIni.h")
args = parser.parse_args()
assert (args.simpleini / "SimpleIni.h").is_file()
w = Path(tempfile.mkdtemp(prefix="sos-gender-tests-"))
src = Path(__file__).resolve().parents[1] / "src"
vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
installation = subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
vcvars = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
assert vcvars.is_file()

h=(src/'util.h').read_text('utf-8')
settings=h[h.index('enum class SexLabTreatment'):h.index('inline Settings g_settings;')]
u=(src/'util.cpp').read_text('utf-8');start=u.index('void Settings::Load()');settings_io=u[start:u.index('\nnamespace Util {',start)]
k=u.index('constexpr std::array<const char*, Binding::kCount> kKeyIniNames');keys=u[k:u.index('};',k)+2]
l=(src/'SchlongLogic.cpp').read_text('utf-8');start=l.index('\tnamespace {\n\t\tstd::mutex playerGenderMutex');logic=l[start:l.index('\n\tvoid EquipAddon(',start)]
h=(src/'SchlongLogic.h').read_text('utf-8');start=h.index('\tstruct PlayerGenderOverride');decl=h[start:h.index('\n\t//',start)]
storage=(src/'Storage.cpp').read_text('utf-8');start=storage.index('\tnamespace {',storage.index('// SERIALIZATION'));serialization=storage[start:]
pre=r'''#define NOMINMAX
#include <Windows.h>
#include <SimpleIni.h>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <cassert>
namespace RE {
using FormID = std::uint32_t;
struct TESFaction {};
struct TESNPC { bool female = true; FormID GetFormID() { return 14; } };
struct TESObjectARMO { bool pubes = false; };
struct Actor {
    TESNPC base;
    bool player = true;
    int rank = -1;
    int writes = 0;
    bool loaded = true;
    bool Is3DLoaded() { return loaded; }
    FormID GetFormID() { return 14; }
    TESNPC* GetActorBase() { return &base; }
    bool IsPlayerRef() { return player; }
    int GetFactionRank(TESFaction*, bool) { return rank; }
    void AddToFaction(TESFaction*, int value) { rank = value; ++writes; }
    void RemoveFromFaction(TESFaction*) { rank = -1; ++writes; }
};
struct PlayerCharacter : Actor {
    inline static Actor* current = nullptr;
    static Actor* GetSingleton() { return current; }
};
struct TESForm {
    template<class T> static T* LookupByID(FormID) { return PlayerCharacter::current; }
};
}
namespace Util {
constexpr int kDefaultRank = 10, kDefaultChance = 20;
bool IsFemale(RE::TESNPC* actor) { return actor->female; }
bool ArmorHasKeyword(RE::TESObjectARMO* armor, int) { return armor->pubes; }
}
namespace Binding { enum { kPin, kBendUp, kBendDown, kPlayerBendUp, kPlayerBendDown, kCount }; }
namespace Actors { void ApplyOverrides() {} }
namespace SKSE::log {
template<class... Args> void info(Args&&...) {}
template<class... Args> void warn(Args&&...) {}
template<class... Args> void error(Args&&...) {}
}
namespace SKSE {
struct MessagingInterface {
    enum { kDataLoaded, kPreLoadGame, kPostLoadGame, kNewGame };
    struct Message { int type; void* data = nullptr; };
};
struct Tasks {
    std::vector<std::function<void()>> pending;
    void AddTask(std::function<void()> task) { pending.push_back(std::move(task)); }
    void Run() {
        auto tasks = std::move(pending);
        pending.clear();
        for (auto& task : tasks) task();
    }
};
Tasks* GetTaskInterface() { static Tasks tasks; return &tasks; }
struct SerializationInterface {
    struct Record { std::uint32_t type, version; std::vector<unsigned char> data; };
    std::vector<Record> records;
    std::size_t next = 0, cursor = 0;
    bool OpenRecord(std::uint32_t type, std::uint32_t version) {
        records.push_back({type, version, {}});
        return true;
    }
    bool WriteRecordData(const void* data, std::size_t size) {
        auto* bytes = static_cast<const unsigned char*>(data);
        records.back().data.insert(records.back().data.end(), bytes, bytes + size);
        return true;
    }
    template<class T> bool WriteRecordData(const T& data) { return WriteRecordData(&data, sizeof(T)); }
    bool GetNextRecordInfo(std::uint32_t& type, std::uint32_t& version, std::uint32_t& length) {
        if (next == records.size()) return false;
        const auto& record = records[next++];
        type = record.type; version = record.version; length = static_cast<std::uint32_t>(record.data.size()); cursor = 0;
        return true;
    }
    bool ReadRecordData(void* out, std::size_t size) {
        const auto& bytes = records[next - 1].data;
        if (cursor + size > bytes.size()) return false;
        std::memcpy(out, bytes.data() + cursor, size); cursor += size; return true;
    }
    template<class T> bool ReadRecordData(T& out) { return ReadRecordData(&out, sizeof(T)); }
    bool ResolveFormID(RE::FormID oldID, RE::FormID& newID) { newID = oldID; return true; }
};
}
const char* INIPath = "settings-test.ini";
const char* kIniSection = "JSON";
RE::TESFaction genderFaction;
RE::TESFaction* g_SexLabGenderFaction = &genderFaction;
RE::TESFaction* g_schlongifiedFaction = nullptr;
int PubKW = 0;
'''
store_pre=r'''
namespace Storage {
namespace {
std::mutex s_mutex;
struct NPCData { std::string addonName; std::uint8_t rank; };
std::unordered_map<RE::FormID, NPCData> s_npcData;
}
void ClearAllNPCData() { std::lock_guard lock(s_mutex); s_npcData.clear(); }
'''
tests=r'''
int main() {
    using Mode = SexLabTreatment;
    using namespace SchlongLogic;
    RE::TESObjectARMO addon, pubes;
    pubes.pubes = true;
    g_settings.SetSexLabGender({Mode::Futa, Mode::Default});
    int checks = 0;
    // Regression: a player never managed by SOS must retain every existing rank.
    for (int rank : {-1, 0, 1, 2}) {
        for (auto* armor : {static_cast<RE::TESObjectARMO*>(nullptr), &pubes}) {
            for (bool reset : {false, true}) {
                RestorePlayerGenderOverride(std::nullopt);
                RE::Actor player; player.rank = rank;
                UpdateFactions(&player, armor, reset);
                assert(player.rank == rank && player.writes == 0); ++checks;
            }
        }
    }
    // Apply, repeat, save, load and remove: restore the captured prior rank.
    for (int prior : {-1, 0, 1, 2}) {
        RestorePlayerGenderOverride(std::nullopt);
        RE::Actor player; player.rank = prior;
        UpdateFactions(&player, &addon, false);
        assert(player.rank == 2);
        const int writes = player.writes;
        UpdateFactions(&player, &addon, false);
        assert(player.writes == writes);
        SKSE::SerializationInterface save;
        Storage::s_npcData[42] = {"example-addon", 7};
        Storage::SaveCallback(&save);
        BeginSaveTransition();
        Storage::RevertCallback(nullptr);
        assert(!GetPlayerGenderOverride());
        Storage::LoadCallback(&save);
        FinishSaveTransition(true);
        assert(Storage::s_npcData.at(42).addonName == "example-addon" && Storage::s_npcData.at(42).rank == 7);
        UpdateFactions(&player, nullptr, false);
        assert(player.rank == prior && !GetPlayerGenderOverride()); ++checks;
    }
    // Later changes from other mods must survive cleanup.
    RestorePlayerGenderOverride(std::nullopt);
    RE::Actor player; player.rank = 0;
    UpdateFactions(&player, &addon, false);
    player.rank = 1;
    int writes = player.writes;
    UpdateFactions(&player, nullptr, true);
    assert(player.rank == 1 && player.writes == writes && !GetPlayerGenderOverride()); ++checks;
    // Mode switches retain the original rank, not an intermediate SOS rank.
    player.rank = -1;
    g_settings.SetSexLabGender({Mode::Futa, Mode::Male});
    UpdateFactions(&player, &addon, false); assert(player.rank == 0);
    g_settings.SetSexLabGender({Mode::Male, Mode::Futa});
    UpdateFactions(&player, &addon, false); assert(player.rank == 2);
    g_settings.SetSexLabGender({Mode::Male, Mode::Default});
    UpdateFactions(&player, &addon, false); assert(player.rank == 0);
    UpdateFactions(&player, &pubes, true); assert(player.rank == -1); ++checks;
    // A male player inherits no female-only global override.
    player.base.female = false;
    g_settings.SetSexLabGender({Mode::Futa, Mode::Futa});
    UpdateFactions(&player, &addon, false); assert(player.rank == 2);
    g_settings.SetSexLabGender({Mode::Futa, Mode::Default});
    UpdateFactions(&player, &addon, false); assert(player.rank == -1); ++checks;
    // Old saves and invalid ownership records must not retain the previous save's owner.
    RestorePlayerGenderOverride(PlayerGenderOverride{0, 2});
    const auto refreshesBeforeLoad = loadedAddonQueries;
    SKSE::SerializationInterface oldSave;
    Storage::LoadCallback(&oldSave); assert(!GetPlayerGenderOverride()); ++checks;
    for (int variant = 0; variant < 4; ++variant) {
        RestorePlayerGenderOverride(PlayerGenderOverride{0, 2});
        SKSE::SerializationInterface bad;
        bad.OpenRecord('PGOV', variant == 0 ? 99 : 1);
        std::int32_t prior = variant == 2 ? -5 : 0;
        std::int32_t applied = variant == 3 ? 50 : 2;
        bad.WriteRecordData(prior);
        if (variant != 1) bad.WriteRecordData(applied);
        Storage::LoadCallback(&bad); assert(!GetPlayerGenderOverride()); ++checks;
    }
    // Drive the real SKSE message handler and queued actor refresh across save boundaries.
    using Message = SKSE::MessagingInterface;
    auto send = [](int type, void* data = nullptr) {
        Message::Message message{type, data};
        OnSKSEMessage(&message);
    };
    auto* success = reinterpret_cast<void*>(1);
    RE::Actor nextPlayer; nextPlayer.rank = 2;
    RE::PlayerCharacter::current = &nextPlayer;
    RestorePlayerGenderOverride(PlayerGenderOverride{0, 2});
    SOS::QueueLoadedPlayerRefresh(); // Old save task.
    QueueSaveOverride(14, GetSaveGeneration()); // Old menu task.
    send(Message::kPreLoadGame);
    Storage::RevertCallback(nullptr);
    SOS::OnActorLoaded(&nextPlayer); // Arrives before PGOV is available.
    assert(nextPlayer.writes == 0);
    SKSE::SerializationInterface newSave;
    newSave.OpenRecord('PGOV', 1);
    newSave.WriteRecordData(std::int32_t{1});
    newSave.WriteRecordData(std::int32_t{2});
    Storage::LoadCallback(&newSave);
    SOS::OnActorLoaded(&nextPlayer); // PGOV is available but load has not completed.
    SOS::QueueLoadedPlayerRefresh(); // Task queued during the load.
    assert(nextPlayer.writes == 0 && !GetPlayerGenderOverride());
    send(Message::kPostLoadGame, success);
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.rank == 1 && nextPlayer.writes == 1 && !GetPlayerGenderOverride());
    assert(loadedAddonQueries == refreshesBeforeLoad + 1);
    assert(savedOverrides == 0);
    QueueSaveOverride(14, GetSaveGeneration());
    SKSE::GetTaskInterface()->Run();
    assert(savedOverrides == 1);
    ++checks;

    nextPlayer.rank = 2; nextPlayer.writes = 0;
    send(Message::kPreLoadGame);
    send(Message::kPostLoadGame, success); // Missing cosave: no serialization callback.
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.rank == 2 && nextPlayer.writes == 0);
    ++checks;

    RestorePlayerGenderOverride(PlayerGenderOverride{0, 2});
    send(Message::kPreLoadGame);
    send(Message::kPostLoadGame); // Failure before Revert leaves the old world intact.
    assert(nextPlayer.writes == 0 && CanRunSaveTask(GetSaveGeneration()));
    assert(GetPlayerGenderOverride()->previousRank == 0);
    Storage::RevertCallback(nullptr); // Standalone script reload.
    assert(CanRunSaveTask(GetSaveGeneration()) && GetPlayerGenderOverride());
    ++checks;

    send(Message::kPreLoadGame);
    Storage::RevertCallback(nullptr);
    newSave.next = 0;
    Storage::LoadCallback(&newSave);
    send(Message::kPostLoadGame); // Failed load never writes faction state.
    SOS::OnActorLoaded(&nextPlayer);
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.rank == 2 && nextPlayer.writes == 0 && !GetPlayerGenderOverride());
    assert(CanRunSaveTask(GetSaveGeneration()));
    ++checks;

    send(Message::kPreLoadGame);
    newSave.next = 0;
    Storage::LoadCallback(&newSave);
    nextPlayer.loaded = false;
    send(Message::kPostLoadGame, success);
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.writes == 0);
    nextPlayer.loaded = true;
    SKSE::GetTaskInterface()->Run(); // Retry succeeds without another actor event.
    assert(nextPlayer.rank == 1 && nextPlayer.writes == 1);
    ++checks;

    nextPlayer.loaded = false; nextPlayer.writes = 0;
    send(Message::kPreLoadGame);
    send(Message::kPostLoadGame, success);
    const auto delaysBeforeLimit = delayedRefreshes;
    for (int i = 0; i < 21; ++i) SKSE::GetTaskInterface()->Run();
    assert(SKSE::GetTaskInterface()->pending.empty() && nextPlayer.writes == 0);
    assert(delayedRefreshes == delaysBeforeLimit + 20);
    SOS::QueueLoadedPlayerRefresh();
    SKSE::GetTaskInterface()->Run();
    send(Message::kPreLoadGame);
    nextPlayer.loaded = true;
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.writes == 0 && SKSE::GetTaskInterface()->pending.empty());
    ++checks;

    nextPlayer.rank = 2; nextPlayer.writes = 0;
    RestorePlayerGenderOverride(PlayerGenderOverride{0, 2});
    send(Message::kNewGame);
    SKSE::GetTaskInterface()->Run();
    assert(nextPlayer.rank == 2 && nextPlayer.writes == 0 && !GetPlayerGenderOverride());
    ++checks;

    // Actual INI methods: conflicting booleans, roundtrip and missing new keys.
    std::ofstream(INIPath) << "[JSON]\nSexLabForceMaleOnSchlong=true\nSexLabForceFutaOnSchlong=true\nSexLabForcePlayerMaleOnSchlong=true\nSexLabForcePlayerFutaOnSchlong=true\n";
    Settings setting; setting.Load();
    auto modes = setting.GetSexLabGender(); assert(modes.global == Mode::Futa && modes.player == Mode::Futa);
    setting.SetSexLabGender({Mode::Male, Mode::Futa}); setting.Save();
    Settings reloaded; reloaded.Load(); modes = reloaded.GetSexLabGender();
    assert(modes.global == Mode::Male && modes.player == Mode::Futa);
    std::ofstream(INIPath) << "[JSON]\nSexLabForceFutaOnSchlong=true\n";
    reloaded.Load(); assert(reloaded.GetSexLabGender().player == Mode::Default); ++checks;
    // Concurrent publication must never expose a pair assembled from different writes.
    Settings concurrent;
    concurrent.SetSexLabGender({Mode::Male, Mode::Futa});
    std::atomic<bool> done{false};
    std::thread writer([&] {
        for (int i = 0; i < 1000000; ++i) {
            concurrent.SetSexLabGender({Mode::Futa, Mode::Male});
            concurrent.SetSexLabGender({Mode::Male, Mode::Futa});
        }
        done.store(true);
    });
    do {
        const auto pair = concurrent.GetSexLabGender();
        assert((pair.global == Mode::Male && pair.player == Mode::Futa) || (pair.global == Mode::Futa && pair.player == Mode::Male));
    } while (!done.load());
    writer.join();
    std::printf("%d ownership/config/save regression checks passed; 2,000,000 concurrent snapshot writes passed\n", checks);
}
'''

menu=(src/'Menu.cpp').read_text('utf-8')
a=menu.index('\t\t\tauto genderModes = g_settings.GetSexLabGender();')
b=menu.index('\n\t\t\tif (!s_status.empty())',a)
ui_pre=r'''
std::string selectedCheckbox;
std::vector<bool> refreshTargets;
namespace Gui {
void SeparatorText(const char*) {}
bool Checkbox(const char* label, bool* value) {
    if (selectedCheckbox != label) return false;
    *value = !*value;
    return true;
}
}
void Tooltip(const char*) {}
void QueueSyncSexLabGender(bool includePinned = true) { refreshTargets.push_back(includePinned); }
void RenderGenderSettings() {
'''
ui_checks=r'''
    g_settings.SetSexLabGender({Mode::Futa, Mode::Default});
    selectedCheckbox = "Force male treatment on player schlong";
    RenderGenderSettings();
    assert(g_settings.GetSexLabGender().global == Mode::Futa && g_settings.GetSexLabGender().player == Mode::Male);
    selectedCheckbox = "Force futa treatment on player schlong";
    RenderGenderSettings();
    assert(g_settings.GetSexLabGender().global == Mode::Futa && g_settings.GetSexLabGender().player == Mode::Futa);
    selectedCheckbox = "Force male treatment on female schlong";
    RenderGenderSettings();
    assert(g_settings.GetSexLabGender().global == Mode::Male && g_settings.GetSexLabGender().player == Mode::Futa);
    selectedCheckbox = "Force futa treatment on player schlong";
    RenderGenderSettings();
    assert(g_settings.GetSexLabGender().global == Mode::Male && g_settings.GetSexLabGender().player == Mode::Default);
    assert(refreshTargets == std::vector<bool>({false, false, true, false}));
    std::printf("Actual menu callbacks: mutual exclusion, priority and targeted refresh passed\n");
'''
tests=tests.replace('    // Concurrent publication',ui_checks+'\n    // Concurrent publication')

events = (src / 'Schlongification.cpp').read_text('utf-8')
actor_loaded = events[events.index('\t\tvoid OnActorLoaded('):events.index('\n\t\t// Underwear')]
queued_refresh = events[events.index('\tvoid TryLoadedPlayerRefresh('):events.index('\n\tvoid RegisterEvents()')]
save_override = menu[menu.index('\t\tvoid QueueSaveOverride('):menu.index('\n\t\tvoid ChangeAddon(')]
main = (src / 'main.cpp').read_text('utf-8')
message_handler = main[main.index('\tvoid OnSKSEMessage('):main.index('\n}\n\nSKSEPluginLoad')]
load_stubs = r'''
int loadedAddonQueries = 0;
int savedOverrides = 0;
int delayedRefreshes = 0;
namespace Actors { void SaveOverride(RE::TESNPC*) { ++savedOverrides; } }
namespace SchlongLogic {
void UpdateFactions(RE::Actor*, RE::TESObjectARMO*, bool = false);
RE::TESObjectARMO* DetermineWinningAddon(RE::Actor*) { ++loadedAddonQueries; return nullptr; }
void EquipAddon(RE::Actor*, RE::TESObjectARMO*) {}
void ScaleSchlongBones(RE::FormID) {}
}
namespace SOS {
bool NeedsEquip(RE::Actor*, RE::TESObjectARMO*) { return false; }
namespace {
std::optional<std::uint64_t> lastPlayerRefresh;
void DelayPlayerRefresh(std::function<void()> task) {
    ++delayedRefreshes;
    SKSE::GetTaskInterface()->AddTask(std::move(task));
}
'''

(w/'regression.cpp').write_text(pre+keys+'\n'+settings+'\nSettings g_settings;\n'+settings_io+'\nnamespace SchlongLogic {\n'+decl+logic+'\n}\n'+store_pre+serialization+ui_pre+menu[a:b]+'\n}\n'+load_stubs+actor_loaded+queued_refresh+'\n}\n'+save_override+'\nvoid OnDataLoaded() {}\n'+message_handler+tests,'utf-8')
inc=args.simpleini.resolve()
command = "@echo off\n" + f'call "{vcvars}" >nul\n' + f'cl /nologo /std:c++latest /EHsc /utf-8 /I"{inc}" regression.cpp /Fe:regression.exe\n' + "if errorlevel 1 exit /b %errorlevel%\nregression.exe\nexit /b %errorlevel%\n"
(w / "test.cmd").write_text(command, encoding="utf-8")
print(f"Test artifacts: {w}", flush=True)
subprocess.run(["cmd", "/d", "/c", "test.cmd"], cwd=w, check=True)
