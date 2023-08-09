<template>
  <div id="app">
    <h1>Welcome to Vue Project</h1>
  </div>
</template>

<script>
import Vue from 'vue'

export default Vue.component('App', {
  data() {
    return {
      message: 'Welcome to Vue Project'
    }
  }
})
</script>

<style scoped>
h1 {
  color: #42b983;
}
</style>