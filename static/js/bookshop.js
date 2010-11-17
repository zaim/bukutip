(function($){

	$.Bookshop = {};

	$.Bookshop.init = function(isbn, title, author){
		var	rows = $('#book-'+isbn+'-prices tbody>tr'),
			loaded = 0,
			total = rows.length,
			lowest_price = null,
			lowest_elem = null,
			completed = function(){
				$(lowest_elem).addClass('lowest').find('th').append('<span>lowest</span>');
				$('#wait').remove();
			};

		rows.each(function(){
			var	name = this.className,
				data = {
					"isbn": isbn,
					"title": title,
					"author": author,
					"shop": name
				},
				row = $(this),
				ptd = row.find('td');

			ptd.addClass('loading').text('loading');

			$.get('/price', data, function(js, status, xhr){
				var prices=JSON.parse(js), price=0, obj=null;

				row.addClass('loaded')
				ptd.removeClass('loading').text('');

				if (prices.error) {
					ptd.addClass('none').text('none');
				}
				else {
					if (prices.length > 0) {
						obj = prices[0]
						price = obj['price'].toFixed(2);
						ptd.html('<a href="'+obj['url']+'">'+price+'</a>');
						if (lowest_price == null) {
							lowest_price = price;
							lowest_elem  = row;
						}
						else {
							if (price < lowest_price) {
								lowest_price = price;
								lowest_elem  = row;
							}
						}
					}
					else {
						ptd.addClass('none').text('none');
					}
				}

				loaded = loaded + 1;
				if (loaded >= total) {
					completed();
				}
			}, 'application/json');
		});

		rows.click(function(){
			var row = $(this);
			if (!row.hasClass('loaded')) {
				return;
			}
			var url = row.find('a').attr('href');
			if (url) {
				window.location = url;
			}
		});
	};

})(jQuery);
