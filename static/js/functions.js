window.addEventListener('DOMContentLoaded', function() {
  document.querySelector('#toggle-tree').addEventListener('click', function(){
    document.querySelector('#tree').classList.toggle('tree')
    document.querySelector('#tree').classList.toggle('list')
  })
})