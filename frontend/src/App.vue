<script setup lang="ts"></script>

<template>
  <!-- Keep browsing pages and loaded cursor batches alive during full-screen reading. -->
  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <KeepAlive include="AppShell">
        <component :is="Component" />
      </KeepAlive>
    </Transition>
  </RouterView>
</template>
