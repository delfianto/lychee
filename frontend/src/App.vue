<script setup lang="ts"></script>

<template>
  <!-- Top-level view only swaps between the app shell and the full-screen
       reader, so a plain fade covers entering/leaving the reader. -->
  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
</template>
