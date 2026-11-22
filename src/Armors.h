#pragma once

namespace Armors {

	// Reads SOS_ARMO_Override.JSON, the manual changes made through the menu
	void LoadOverrides();

	// Forgets the overrides loaded in memory, the JSON is not touched
	void ClearOverrides();

	// Applies overrides, keywords and the startup default to body armor slots
	void ProcessArmors();

	// Makes an armor revealing (no slot 52) or concealing (slot 52) and remembers it in the JSON.
	// Game thread only (the overrides are not locked).
	bool SetOverride(RE::TESObjectARMO* a_armor, bool a_revealing);

	// Unequips what hides the addon: the armor in slot 52 (if it isn't the addon) and the underwear.
	// It exists for mods that replace all the outfits. Game thread only.
	void RemoveConcealing(RE::Actor* a_actor);
}
