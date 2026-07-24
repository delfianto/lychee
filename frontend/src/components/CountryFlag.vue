<script setup lang="ts">
import cn from "flag-icons/flags/4x3/cn.svg";
import de from "flag-icons/flags/4x3/de.svg";
import fr from "flag-icons/flags/4x3/fr.svg";
import gb from "flag-icons/flags/4x3/gb.svg";
import id from "flag-icons/flags/4x3/id.svg";
import jp from "flag-icons/flags/4x3/jp.svg";
import kr from "flag-icons/flags/4x3/kr.svg";
import th from "flag-icons/flags/4x3/th.svg";
import tw from "flag-icons/flags/4x3/tw.svg";
import us from "flag-icons/flags/4x3/us.svg";
import vn from "flag-icons/flags/4x3/vn.svg";
import { computed } from "vue";

// Only the origin countries lychee uses. Importing individual SVGs keeps the
// bundle tiny — the flag-icons global CSS pulls in ~250 flags (~500 kB).
const FLAGS: Record<string, string> = { cn, de, fr, gb, id, jp, kr, th, tw, us, vn };

const props = defineProps<{ cc: string }>();
const src = computed(() => FLAGS[props.cc.toLowerCase()]);
const label = computed(() => props.cc.toUpperCase());
</script>

<template>
  <img v-if="src" :src="src" :alt="label" :title="label" class="inline-block h-4 w-auto shrink-0 rounded-sm" />
</template>
