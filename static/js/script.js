document.addEventListener("DOMContentLoaded", () => {
	
});

window.addEventListener("load", (event) => {

  header_humburger();
  section_hero();
  section_cats();
  section_rating();
  section_profile_mob();

})

function header_humburger(){
  
  const btn  = document.querySelector(".header--burger");
  const menu = document.querySelector(".header__menu");

  if (!btn || !menu) return;

  // Открытие/закрытие меню только по клику на бургер
  btn.addEventListener("click", function(e){
    e.preventDefault();
    e.stopPropagation();
    btn.classList.toggle("active");
    menu.classList.toggle("active");
  });

  // Закрытие меню при клике вне его области
  document.addEventListener('click', function(e) {
    if (menu.classList.contains('active')) {
      // Если клик был не на меню и не на бургер, закрываем меню
      if (!menu.contains(e.target) && !btn.contains(e.target)) {
        btn.classList.remove("active");
        menu.classList.remove("active");
      }
    }
  });
}

function section_hero(){
  if(document.querySelector("section.hero")){

    const hero    = document.querySelector("section.hero");
    const banner  = document.querySelector("section.banner");
    const heroBtn = hero.querySelector(".hero--btn");

    heroBtn.addEventListener("click", function(){
      window.scroll({
        top: banner.offsetTop + 300,
        left: 0,
        behavior: "smooth",
      }); 
    })
  }
}
function section_cats(){
  if(document.querySelector("section.cats")){

    const section = document.querySelector("section.cats");
    const allBtns = section.querySelectorAll(".cats__nav--item");
    const allTabs = section.querySelectorAll(".cats__tab");

    allBtns.forEach((btn) => {
      btn.addEventListener("click", function(){
        
        allBtns.forEach((btn2) => { btn2.classList.remove("active"); })
        allTabs.forEach((tab) => { tab.classList.remove("active"); })

        let tabNumber = parseInt(btn.getAttribute("data-open-tab"));
        btn.classList.add("active");
        allTabs[tabNumber].classList.add("active");
        
      })
    })
  }
}

function section_rating(){
  if(document.querySelector("section.rating")){

    const section = document.querySelector("section.rating");
    const allBtns = section.querySelectorAll(".rating__nav--item");
    const allTabs = section.querySelectorAll(".rating__tab");
    const search = section.querySelector(".rating__search--input");
    const allItems = section.querySelectorAll(".rating__tab__item")
    const searchNo = section.querySelector(".rating--nothing")

    allBtns.forEach((btn) => {
      btn.addEventListener("click", function(){
        
        allBtns.forEach((btn2) => { btn2.classList.remove("active"); })
        allTabs.forEach((tab) => { tab.classList.remove("active"); })

        let tabNumber = parseInt(btn.getAttribute("data-open-tab"));
        btn.classList.add("active");
        allTabs[tabNumber].classList.add("active");
        
      })
    })

    search.addEventListener("input", function(){

      let val = search.value.toLowerCase();
      let count = 0;
      allItems.forEach((item) => {

        let itemId = item.querySelector(".rating__tabs__col-1").textContent.toLowerCase();
        let itemName = item.querySelector(".rating__tabs__col-3").textContent.toLowerCase();

        if(itemId.includes(val) || itemName.includes(val) || val == ""){
          item.classList.remove("hide");
          count++;
        } else {
          item.classList.add("hide");
        }
      })

      if(count == 0){
        searchNo.style.display = "block";
      } else {
        searchNo.style.display = "none";
      }
    })
  }
}

function section_profile_mob(){
  if(document.querySelector("section.profile") && window.innerWidth <= 880){

    const section = document.querySelector("section.profile");
    const allTitles = section.querySelectorAll(".profile--title");
    const openPopup = section.querySelector(".profile__open--btn");
    const popup     = section.querySelector(".profile__qr-show");
    const popupClose = popup.querySelector(".profile--go-back");

    allTitles.forEach((item) => {
      item.addEventListener("click", function(){
        item.classList.toggle("active");
      })
    })

    openPopup.addEventListener("click", function(){
      popup.classList.add("active");
    })
    popupClose.addEventListener("click", function(){
      popup.classList.remove("active");
    })
  }
}
